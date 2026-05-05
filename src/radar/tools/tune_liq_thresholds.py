"""Live calibration helper for ``liq_cascade`` thresholds.

Listens to the Binance ``forceOrder`` WebSocket for a fixed window, samples
the 1h aggregator state at a regular cadence, and prints percentile
distributions plus threshold recommendations split by major/minor asset
class.

Exists because Binance's public REST does not expose historical liquidation
data, so calibration has to be done live.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime

from loguru import logger

from radar.config import get_settings
from radar.modules.derivatives.liq_aggregator import (
    LiquidationAggregator,
    LiquidationEvent,
)
from radar.modules.derivatives.universe import is_major
from radar.sources.binance_ws import BinanceLiquidationStream


@dataclass(frozen=True, slots=True)
class Sample:
    """One snapshot of an asset's 1h aggregator state."""

    symbol: str
    ts: datetime
    long_usd: float
    short_usd: float


@dataclass(frozen=True, slots=True)
class ThresholdRecommendation:
    """Output of :func:`compute_threshold_recommendations`."""

    sample_count: int
    major_p90: float
    major_p95: float
    major_p99: float
    minor_p90: float
    minor_p95: float
    minor_p99: float
    per_symbol_p95: dict[str, float] = field(default_factory=dict)


def percentile(values: list[float], q: float) -> float:
    """Return the ``q``-quantile (``0 <= q <= 1``) of ``values``.

    Uses linear interpolation between the two nearest ranks. Returns ``0.0``
    for an empty list and the single value when there is only one sample.
    Stdlib ``statistics.quantiles`` is fine for many problems but its
    boundary behaviour for tiny samples is awkward, so we hand-roll the
    interpolation here.
    """
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q must be in [0, 1], got {q}")
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    sorted_values = sorted(values)
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def compute_threshold_recommendations(
    samples: Iterable[Sample],
) -> ThresholdRecommendation:
    """Aggregate per-class peaks (max of long, short) across all samples."""
    sample_list = list(samples)
    major_peaks: list[float] = []
    minor_peaks: list[float] = []
    by_symbol: defaultdict[str, list[float]] = defaultdict(list)
    for s in sample_list:
        peak = max(s.long_usd, s.short_usd)
        by_symbol[s.symbol].append(peak)
        (major_peaks if is_major(s.symbol) else minor_peaks).append(peak)
    per_symbol_p95 = {sym: percentile(vals, 0.95) for sym, vals in by_symbol.items()}
    return ThresholdRecommendation(
        sample_count=len(sample_list),
        major_p90=percentile(major_peaks, 0.90),
        major_p95=percentile(major_peaks, 0.95),
        major_p99=percentile(major_peaks, 0.99),
        minor_p90=percentile(minor_peaks, 0.90),
        minor_p95=percentile(minor_peaks, 0.95),
        minor_p99=percentile(minor_peaks, 0.99),
        per_symbol_p95=per_symbol_p95,
    )


def format_summary(rec: ThresholdRecommendation, *, top_n: int = 15) -> str:
    """Render the recommendation as a human-readable text block."""

    def m(v: float) -> str:
        return f"${v / 1e6:>7.2f}M"

    lines: list[str] = [
        f"Tuner summary ({rec.sample_count} samples)",
        "",
        "class | percentile | threshold",
        "------+------------+-----------",
        f"major |        p90 | {m(rec.major_p90)}",
        f"major |        p95 | {m(rec.major_p95)}",
        f"major |        p99 | {m(rec.major_p99)}",
        f"minor |        p90 | {m(rec.minor_p90)}",
        f"minor |        p95 | {m(rec.minor_p95)}",
        f"minor |        p99 | {m(rec.minor_p99)}",
        "",
        "Suggested update to LiquidationCascadeRule:",
        f"  major_threshold_usd = {int(rec.major_p95):>16,}",
        f"  minor_threshold_usd = {int(rec.minor_p95):>16,}",
    ]

    top = sorted(rec.per_symbol_p95.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    if top:
        lines.extend(
            [
                "",
                f"Top {len(top)} symbols by p95 peak liquidation:",
                "symbol      | p95",
                "------------+-----------",
            ]
        )
        for sym, val in top:
            lines.append(f"{sym:<11} | {m(val)}")
    return "\n".join(lines)


async def run_tuner(
    *,
    minutes: float,
    sample_interval_sec: float,
    url: str | None = None,
) -> ThresholdRecommendation:
    """Drive the WS for ``minutes`` and return the recommendation.

    Cancellable: ``KeyboardInterrupt`` / task cancellation surface a partial
    recommendation built from samples collected so far.
    """
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    if sample_interval_sec <= 0:
        raise ValueError("sample_interval_sec must be positive")

    aggregator = LiquidationAggregator()

    def _on_event(event: LiquidationEvent) -> None:
        aggregator.record(event)

    if url:
        stream = BinanceLiquidationStream(on_event=_on_event, url=url)
    else:
        stream = BinanceLiquidationStream(on_event=_on_event)

    samples: list[Sample] = []
    deadline = asyncio.get_event_loop().time() + minutes * 60.0
    stream_task = asyncio.create_task(stream.run(), name="binance_ws_tune")
    try:
        while asyncio.get_event_loop().time() < deadline:
            remaining = deadline - asyncio.get_event_loop().time()
            await asyncio.sleep(min(sample_interval_sec, max(0.1, remaining)))
            now = datetime.now(UTC)
            for sym in aggregator.tracked_symbols():
                long_usd, short_usd = aggregator.totals(sym, now=now)
                samples.append(Sample(symbol=sym, ts=now, long_usd=long_usd, short_usd=short_usd))
            logger.info(
                "tune: {} samples so far; tracking {} symbols",
                len(samples),
                len(aggregator.tracked_symbols()),
            )
    finally:
        stream.stop()
        stream_task.cancel()
        with suppress(asyncio.CancelledError):
            await stream_task

    return compute_threshold_recommendations(samples)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="radar-tune",
        description="Calibrate liq_cascade thresholds from a live Binance forceOrder window.",
    )
    parser.add_argument(
        "--minutes",
        type=float,
        default=60.0,
        help="Total observation window in minutes (default: 60).",
    )
    parser.add_argument(
        "--sample-interval-sec",
        type=float,
        default=60.0,
        help="Seconds between aggregator snapshots (default: 60).",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Override the Binance forceOrder WebSocket URL "
        "(falls back to BINANCE_FORCEORDER_WS_URL or the public default).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    url = args.url
    if url is None:
        url = get_settings().binance_forceorder_ws_url
    rec = asyncio.run(
        run_tuner(
            minutes=args.minutes,
            sample_interval_sec=args.sample_interval_sec,
            url=url,
        )
    )
    print(format_summary(rec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
