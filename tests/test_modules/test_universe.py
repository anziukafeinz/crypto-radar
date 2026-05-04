"""Universe parsing & helpers."""

from __future__ import annotations

from radar.modules.derivatives.universe import (
    DEFAULT_PERPETUALS,
    is_major,
    parse_universe,
    to_binance,
)


def test_to_binance_uppercases_and_appends_usdt() -> None:
    assert to_binance("btc") == "BTCUSDT"
    assert to_binance("ETH") == "ETHUSDT"


def test_is_major_only_for_btc_and_eth() -> None:
    assert is_major("BTC") is True
    assert is_major("eth") is True
    assert is_major("SOL") is False


def test_parse_universe_returns_defaults_when_empty() -> None:
    assert parse_universe(None) == list(DEFAULT_PERPETUALS)
    assert parse_universe("") == list(DEFAULT_PERPETUALS)
    assert parse_universe("   ") == list(DEFAULT_PERPETUALS)


def test_parse_universe_respects_override_and_normalises() -> None:
    assert parse_universe("btc, eth ,sol") == ["BTC", "ETH", "SOL"]
