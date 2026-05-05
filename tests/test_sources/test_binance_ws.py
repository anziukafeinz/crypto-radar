"""Tests for the Binance ``forceOrder`` WebSocket source."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from radar.sources.binance_ws import parse_force_order


def _frame(**order_overrides: object) -> str:
    """Build a Binance ``forceOrder`` JSON frame with sane defaults."""
    order = {
        "s": "BTCUSDT",
        "S": "SELL",
        "o": "LIMIT",
        "f": "IOC",
        "q": "0.014",
        "p": "9910",
        "ap": "9910",
        "X": "FILLED",
        "l": "0.014",
        "z": "0.014",
        "T": 1_568_014_460_893,
    }
    order.update(order_overrides)  # type: ignore[arg-type]
    payload = {"e": "forceOrder", "E": 1_568_014_460_893, "o": order}
    return json.dumps(payload)


def test_parse_long_liquidation() -> None:
    raw = _frame(s="BTCUSDT", S="SELL", z="0.5", ap="50000")
    event = parse_force_order(raw)
    assert event is not None
    assert event.symbol == "BTC"
    assert event.side == "long"
    assert event.usd == 25_000.0
    assert event.ts == datetime(2019, 9, 9, 7, 34, 20, 893_000, tzinfo=UTC)


def test_parse_short_liquidation() -> None:
    raw = _frame(s="ETHUSDT", S="BUY", z="2", ap="3000")
    event = parse_force_order(raw)
    assert event is not None
    assert event.symbol == "ETH"
    assert event.side == "short"
    assert event.usd == 6_000.0


def test_parse_strips_1000_prefix() -> None:
    raw = _frame(s="1000PEPEUSDT", S="SELL", z="1000000", ap="0.001")
    event = parse_force_order(raw)
    assert event is not None
    assert event.symbol == "PEPE"
    assert event.usd == 1_000.0


def test_parse_drops_non_usdt_perp() -> None:
    raw = _frame(s="BTCBUSD", S="SELL")
    assert parse_force_order(raw) is None


def test_parse_drops_non_force_order_event() -> None:
    payload = json.dumps({"e": "trade", "p": "100"})
    assert parse_force_order(payload) is None


def test_parse_drops_zero_value() -> None:
    raw = _frame(z="0", ap="0")
    assert parse_force_order(raw) is None


def test_parse_drops_unknown_side() -> None:
    raw = _frame(S="HOLD")
    assert parse_force_order(raw) is None


def test_parse_handles_malformed_json() -> None:
    assert parse_force_order("not json") is None
    assert parse_force_order(b"{}") is None
