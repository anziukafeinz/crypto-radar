"""Tests for the in-memory liquidation aggregator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from radar.modules.derivatives.liq_aggregator import (
    LiquidationAggregator,
    LiquidationEvent,
)


def _ev(symbol: str, side: str, usd: float, ts: datetime) -> LiquidationEvent:
    # Cast via str -> Literal at construction time; the dataclass accepts.
    return LiquidationEvent(symbol=symbol, side=side, usd=usd, ts=ts)  # type: ignore[arg-type]


def test_invalid_window_rejected() -> None:
    with pytest.raises(ValueError):
        LiquidationAggregator(window_seconds=0)
    with pytest.raises(ValueError):
        LiquidationAggregator(window_seconds=-1)


def test_totals_split_by_side() -> None:
    agg = LiquidationAggregator(window_seconds=3600)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    agg.record(_ev("BTC", "long", 1_000_000, now - timedelta(minutes=5)))
    agg.record(_ev("BTC", "long", 500_000, now - timedelta(minutes=1)))
    agg.record(_ev("BTC", "short", 250_000, now))

    long_usd, short_usd = agg.totals("BTC", now=now)
    assert long_usd == pytest.approx(1_500_000.0)
    assert short_usd == pytest.approx(250_000.0)


def test_totals_evicts_outside_window() -> None:
    agg = LiquidationAggregator(window_seconds=3600)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    # Insert one stale event (>1h ago) and one recent event.
    agg.record(_ev("ETH", "long", 9_999_999, now - timedelta(hours=2)))
    agg.record(_ev("ETH", "long", 100_000, now - timedelta(minutes=10)))

    long_usd, short_usd = agg.totals("ETH", now=now)
    assert long_usd == pytest.approx(100_000.0)
    assert short_usd == 0.0
    # Stale events are evicted from storage entirely.
    assert agg.event_count("ETH") == 1


def test_totals_unknown_symbol_returns_zero() -> None:
    agg = LiquidationAggregator()
    long_usd, short_usd = agg.totals("DOGE")
    assert (long_usd, short_usd) == (0.0, 0.0)


def test_per_symbol_isolation() -> None:
    agg = LiquidationAggregator()
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    agg.record(_ev("BTC", "long", 1.0, now))
    agg.record(_ev("ETH", "short", 2.0, now))

    btc_long, btc_short = agg.totals("BTC", now=now)
    eth_long, eth_short = agg.totals("ETH", now=now)
    assert (btc_long, btc_short) == (1.0, 0.0)
    assert (eth_long, eth_short) == (0.0, 2.0)


def test_tracked_symbols_after_eviction() -> None:
    agg = LiquidationAggregator(window_seconds=60)
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    agg.record(_ev("BTC", "long", 1.0, t0))
    agg.record(_ev("ETH", "long", 1.0, t0))
    # Force eviction by querying past the window.
    later = t0 + timedelta(minutes=5)
    agg.totals("BTC", now=later)
    agg.totals("ETH", now=later)
    assert agg.tracked_symbols() == []
