"""Binance adapter tests using httpx.MockTransport (no live network)."""

from __future__ import annotations

import httpx
import pytest

from radar.sources.binance import Binance


def _client(handler):  # type: ignore[no-untyped-def]
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(
        base_url="https://fapi.binance.com",
        transport=transport,
        headers={"User-Agent": "crypto-radar/0.1"},
    )


@pytest.mark.asyncio
async def test_open_interest_returns_float() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fapi/v1/openInterest"
        assert request.url.params["symbol"] == "BTCUSDT"
        return httpx.Response(200, json={"openInterest": "12345.6", "symbol": "BTCUSDT"})

    binance = Binance(client=_client(handler))
    result = await binance.open_interest("BTCUSDT")
    assert result == 12345.6
    await binance.aclose()


@pytest.mark.asyncio
async def test_premium_index_passes_symbol_param() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["symbol"] = request.url.params.get("symbol", "")
        return httpx.Response(
            200,
            json={
                "symbol": "BTCUSDT",
                "markPrice": "50000.0",
                "indexPrice": "49990.0",
                "lastFundingRate": "0.0001",
                "nextFundingTime": 0,
                "interestRate": "0.0001",
                "time": 0,
            },
        )

    binance = Binance(client=_client(handler))
    data = await binance.premium_index("BTCUSDT")
    assert captured["path"] == "/fapi/v1/premiumIndex"
    assert captured["symbol"] == "BTCUSDT"
    assert data["markPrice"] == "50000.0"
    await binance.aclose()


@pytest.mark.asyncio
async def test_open_interest_hist_returns_list() -> None:
    payload = [
        {
            "symbol": "BTCUSDT",
            "sumOpenInterest": "1000",
            "sumOpenInterestValue": "1000000",
            "timestamp": i,
        }
        for i in range(24)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/futures/data/openInterestHist"
        return httpx.Response(200, json=payload)

    binance = Binance(client=_client(handler))
    data = await binance.open_interest_hist("BTCUSDT", period="1h", limit=24)
    assert len(data) == 24
    assert data[0]["sumOpenInterestValue"] == "1000000"
    await binance.aclose()


@pytest.mark.asyncio
async def test_klines_returns_list_of_lists() -> None:
    rows = [[i, "100", "101", "99", str(100 + i), "10"] for i in range(24)]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fapi/v1/klines"
        return httpx.Response(200, json=rows)

    binance = Binance(client=_client(handler))
    data = await binance.klines("BTCUSDT", interval="1h", limit=24)
    assert len(data) == 24
    assert data[-1][4] == "123"
    await binance.aclose()
