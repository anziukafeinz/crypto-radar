"""Binance USDT-margined Futures REST adapter (public, no auth required)."""

from __future__ import annotations

from typing import Any, cast

from radar.sources.base import BaseSource


class Binance(BaseSource):
    """Public endpoints under ``fapi.binance.com``."""

    name = "binance"
    base_url = "https://fapi.binance.com"

    async def open_interest(self, symbol: str) -> float:
        """Return current open interest for ``symbol`` denominated in the base asset."""
        data = await self._get_json("/fapi/v1/openInterest", params={"symbol": symbol})
        return float(data["openInterest"])

    async def open_interest_hist(
        self,
        symbol: str,
        period: str = "1h",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        """Return OI history. Each entry has ``sumOpenInterestValue`` (USD)."""
        data = await self._get_json(
            "/futures/data/openInterestHist",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        return cast(list[dict[str, Any]], data)

    async def premium_index(self, symbol: str | None = None) -> Any:
        """Return latest mark/index price + funding info.

        Without ``symbol`` the response is a list across all perps.
        """
        params = {"symbol": symbol} if symbol else None
        return await self._get_json("/fapi/v1/premiumIndex", params=params)

    async def funding_rate_history(
        self,
        symbol: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return historical funding rates (most recent last)."""
        data = await self._get_json(
            "/fapi/v1/fundingRate", params={"symbol": symbol, "limit": limit}
        )
        return cast(list[dict[str, Any]], data)

    async def klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 24,
    ) -> list[list[Any]]:
        """Return candle history. Index 4 of each entry is the close price."""
        data = await self._get_json(
            "/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        return cast(list[list[Any]], data)

    async def top_long_short_position_ratio(
        self,
        symbol: str,
        period: str = "1h",
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        """Top trader long/short position ratio history."""
        data = await self._get_json(
            "/futures/data/topLongShortPositionRatio",
            params={"symbol": symbol, "period": period, "limit": limit},
        )
        return cast(list[dict[str, Any]], data)
