"""Tests for the Bybit ``allLiquidation`` WebSocket source."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from radar.sources.bybit_ws import parse_all_liquidation


def _frame(*items: dict[str, object], topic: str = "allLiquidation.BTCUSDT") -> str:
    """Build a Bybit ``allLiquidation`` JSON frame with sane defaults."""
    payload = {
        "topic": topic,
        "type": "snapshot",
        "ts": 1_777_990_485_494,
        "data": list(items),
    }
    return json.dumps(payload)


def _item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "T": 1_777_990_485_069,
        "s": "BTCUSDT",
        "S": "Buy",
        "v": "0.5",
        "p": "50000",
    }
    item.update(overrides)
    return item


def test_parse_long_liquidation_buy_side() -> None:
    raw = _frame(_item(s="BTCUSDT", S="Buy", v="0.5", p="50000"))
    events = parse_all_liquidation(raw)
    assert len(events) == 1
    e = events[0]
    assert e.symbol == "BTC"
    # Bybit reports the LIQUIDATED position side; ``Buy`` means a long was liq'd.
    assert e.side == "long"
    assert e.usd == 25_000.0
    assert e.ts == datetime(2026, 5, 5, 14, 14, 45, 69_000, tzinfo=UTC)


def test_parse_short_liquidation_sell_side() -> None:
    raw = _frame(_item(s="ETHUSDT", S="Sell", v="2", p="3000"))
    events = parse_all_liquidation(raw)
    assert len(events) == 1
    e = events[0]
    assert e.symbol == "ETH"
    assert e.side == "short"
    assert e.usd == 6_000.0


def test_parse_strips_1000_prefix() -> None:
    raw = _frame(
        _item(s="1000PEPEUSDT", S="Buy", v="1000000", p="0.001"),
        topic="allLiquidation.1000PEPEUSDT",
    )
    events = parse_all_liquidation(raw)
    assert len(events) == 1
    assert events[0].symbol == "PEPE"
    assert events[0].usd == 1_000.0


def test_parse_drops_non_usdt_perp() -> None:
    raw = _frame(_item(s="BTCUSDC", S="Buy"), topic="allLiquidation.BTCUSDC")
    assert parse_all_liquidation(raw) == []


def test_parse_drops_unknown_topic() -> None:
    payload = json.dumps(
        {
            "topic": "tickers.BTCUSDT",
            "type": "snapshot",
            "ts": 1_777_990_485_494,
            "data": [_item()],
        }
    )
    assert parse_all_liquidation(payload) == []


def test_parse_drops_subscribe_ack() -> None:
    payload = json.dumps(
        {
            "success": True,
            "ret_msg": "",
            "conn_id": "abc",
            "req_id": "",
            "op": "subscribe",
        }
    )
    assert parse_all_liquidation(payload) == []


def test_parse_drops_pong() -> None:
    payload = json.dumps({"op": "pong", "args": ["1777990500000"]})
    assert parse_all_liquidation(payload) == []


def test_parse_drops_zero_value() -> None:
    raw = _frame(_item(v="0", p="0"))
    assert parse_all_liquidation(raw) == []


def test_parse_drops_unknown_side() -> None:
    raw = _frame(_item(S="Hold"))
    assert parse_all_liquidation(raw) == []


def test_parse_handles_malformed_json() -> None:
    assert parse_all_liquidation("not json") == []
    assert parse_all_liquidation(b"{}") == []


def test_parse_emits_multiple_events_per_frame() -> None:
    raw = _frame(
        _item(s="BTCUSDT", S="Buy", v="0.1", p="50000"),
        _item(s="BTCUSDT", S="Sell", v="0.2", p="50100"),
        _item(s="BTCUSDT", S="Buy", v="0.05", p="50050"),
    )
    events = parse_all_liquidation(raw)
    assert len(events) == 3
    assert [e.side for e in events] == ["long", "short", "long"]
    assert events[0].usd == 5_000.0
    assert events[1].usd == 10_020.0
    assert events[2].usd == 2_502.5


def test_parse_falls_back_to_frame_ts_when_item_missing() -> None:
    # If item has no T, the parser falls back to the frame's ts field.
    item: dict[str, object] = {"s": "BTCUSDT", "S": "Buy", "v": "1", "p": "50000"}
    raw = json.dumps(
        {
            "topic": "allLiquidation.BTCUSDT",
            "type": "snapshot",
            "ts": 1_777_990_500_000,
            "data": [item],
        }
    )
    events = parse_all_liquidation(raw)
    assert len(events) == 1
    assert events[0].ts == datetime.fromtimestamp(1_777_990_500_000 / 1000, tz=UTC)


def test_parse_drops_non_dict_items() -> None:
    payload = json.dumps(
        {
            "topic": "allLiquidation.BTCUSDT",
            "type": "snapshot",
            "ts": 1_777_990_485_494,
            "data": ["not a dict", 42, _item()],
        }
    )
    events = parse_all_liquidation(payload)
    assert len(events) == 1
    assert events[0].symbol == "BTC"


def test_parse_drops_when_data_is_not_list() -> None:
    payload = json.dumps(
        {
            "topic": "allLiquidation.BTCUSDT",
            "type": "snapshot",
            "data": _item(),
        }
    )
    assert parse_all_liquidation(payload) == []
