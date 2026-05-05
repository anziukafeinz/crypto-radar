"""Tests for the liq_cascade threshold tuner."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from radar.tools.tune_liq_thresholds import (
    Sample,
    compute_threshold_recommendations,
    format_summary,
    percentile,
)


def test_percentile_empty_list() -> None:
    assert percentile([], 0.5) == 0.0


def test_percentile_single_value() -> None:
    assert percentile([42.0], 0.5) == 42.0
    assert percentile([42.0], 0.99) == 42.0


def test_percentile_interpolates() -> None:
    # 0..10 inclusive -> 11 values; p50 = 5.0, p90 = 9.0
    values = [float(i) for i in range(11)]
    assert percentile(values, 0.0) == 0.0
    assert percentile(values, 0.5) == pytest.approx(5.0)
    assert percentile(values, 0.9) == pytest.approx(9.0)
    assert percentile(values, 1.0) == 10.0


def test_percentile_handles_unsorted_input() -> None:
    values = [5.0, 1.0, 10.0, 3.0, 8.0]
    # Sorted: [1, 3, 5, 8, 10]; p50 = 5.0, p99 ~ 9.92
    assert percentile(values, 0.5) == pytest.approx(5.0)
    assert percentile(values, 0.99) == pytest.approx(9.92)


def test_percentile_rejects_out_of_range_q() -> None:
    with pytest.raises(ValueError):
        percentile([1.0, 2.0], 1.5)
    with pytest.raises(ValueError):
        percentile([1.0, 2.0], -0.1)


def _samples_for(symbol: str, peaks: list[float]) -> list[Sample]:
    """Helper: build a Sample per peak with long_usd = peak, short_usd = 0."""
    base = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    return [Sample(symbol=symbol, ts=base, long_usd=p, short_usd=0.0) for p in peaks]


def test_compute_recommendations_splits_by_class() -> None:
    samples = (
        _samples_for("BTC", [1e6, 2e6, 5e6, 50e6, 100e6])  # major
        + _samples_for("DOGE", [1e5, 2e5, 1e6, 5e6, 20e6])  # minor
    )
    rec = compute_threshold_recommendations(samples)
    assert rec.sample_count == 10
    # p95 of [1e6, 2e6, 5e6, 50e6, 100e6] -> interpolation between 50M and 100M
    assert rec.major_p95 == pytest.approx(90_000_000.0)
    assert rec.minor_p95 == pytest.approx(17_000_000.0)
    assert set(rec.per_symbol_p95) == {"BTC", "DOGE"}


def test_compute_recommendations_uses_max_of_long_and_short() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    samples = [
        Sample(symbol="BTC", ts=base, long_usd=10e6, short_usd=1e6),  # peak 10M
        Sample(symbol="BTC", ts=base, long_usd=1e6, short_usd=80e6),  # peak 80M
    ]
    rec = compute_threshold_recommendations(samples)
    # Two values [10M, 80M] -> p50 (any quantile) interpolates
    assert rec.major_p99 == pytest.approx(80_000_000.0 - 0.01 * 70_000_000.0)
    assert rec.major_p90 == pytest.approx(10_000_000.0 + 0.9 * 70_000_000.0)


def test_compute_recommendations_empty_input() -> None:
    rec = compute_threshold_recommendations([])
    assert rec.sample_count == 0
    assert rec.major_p95 == 0.0
    assert rec.minor_p95 == 0.0
    assert rec.per_symbol_p95 == {}


def test_format_summary_lists_top_symbols_by_p95() -> None:
    rec = compute_threshold_recommendations(
        _samples_for("BTC", [10e6, 20e6]) + _samples_for("ETH", [5e6]) + _samples_for("DOGE", [1e6])
    )
    text = format_summary(rec)
    assert "Tuner summary (4 samples)" in text
    assert "major_threshold_usd" in text
    assert "minor_threshold_usd" in text
    assert "BTC" in text
    assert "DOGE" in text
    btc_idx = text.index("BTC")
    doge_idx = text.index("DOGE")
    # BTC has the highest p95, must appear before DOGE in the per-symbol list.
    assert btc_idx < doge_idx
