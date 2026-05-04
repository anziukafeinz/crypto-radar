"""Pull derivatives data, persist as metrics, evaluate alert rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from radar.alerts.dispatcher import TelegramNotifier
from radar.alerts.engine import AlertEngine, RuleContext
from radar.db.models import Metric
from radar.modules.derivatives.universe import is_major, to_binance
from radar.sources.base import SourceError
from radar.sources.binance import Binance


class DerivativesPoller:
    """Coordinates source pulls + metric persistence + alert evaluation."""

    def __init__(
        self,
        binance: Binance,
        sessionmaker: async_sessionmaker[AsyncSession],
        engine: AlertEngine,
        notifier: TelegramNotifier,
        universe: list[str],
    ) -> None:
        self._binance = binance
        self._sessionmaker = sessionmaker
        self._engine = engine
        self._notifier = notifier
        self._universe = universe

    async def poll(self) -> None:
        """Single poll cycle across the entire universe."""
        logger.info("Derivatives poll start ({} symbols)", len(self._universe))
        for symbol in self._universe:
            try:
                await self.poll_symbol(symbol)
            except SourceError as exc:
                logger.warning("{}: source error {}", symbol, exc)
            except Exception:
                logger.exception("Unexpected failure polling {}", symbol)
        logger.info("Derivatives poll done")

    async def poll_symbol(self, symbol: str) -> None:
        binance_symbol = to_binance(symbol)
        prem = await self._binance.premium_index(binance_symbol)
        oi_hist = await self._binance.open_interest_hist(binance_symbol, period="1h", limit=24)
        klines = await self._binance.klines(binance_symbol, interval="1h", limit=24)

        snapshot = self._build_snapshot(symbol, prem, oi_hist, klines)
        await self._persist_snapshot(symbol, snapshot)
        await self._evaluate(symbol, snapshot)

    def _build_snapshot(
        self,
        symbol: str,
        prem: dict[str, Any],
        oi_hist: list[dict[str, Any]],
        klines: list[list[Any]],
    ) -> dict[str, Any]:
        if not oi_hist or not klines:
            raise SourceError(f"{symbol}: empty OI history or klines")
        oi_now = float(oi_hist[-1]["sumOpenInterestValue"])
        oi_24h_ago = float(oi_hist[0]["sumOpenInterestValue"])
        price_now = float(klines[-1][4])
        price_24h_ago = float(klines[0][4])
        return {
            "binance_symbol": to_binance(symbol),
            "mark_price": float(prem["markPrice"]),
            "index_price": float(prem["indexPrice"]),
            "funding_rate": float(prem["lastFundingRate"]),
            "oi_now_usd": oi_now,
            "oi_24h_ago_usd": oi_24h_ago,
            "price_now": price_now,
            "price_24h_ago": price_24h_ago,
            "is_major": is_major(symbol),
        }

    async def _persist_snapshot(self, symbol: str, snapshot: dict[str, Any]) -> None:
        ts = datetime.now(UTC).replace(tzinfo=None)
        metric_fields = (
            "mark_price",
            "index_price",
            "funding_rate",
            "oi_now_usd",
            "oi_24h_ago_usd",
            "price_now",
            "price_24h_ago",
        )
        async with self._sessionmaker() as session:
            for name in metric_fields:
                value = snapshot.get(name)
                if isinstance(value, int | float):
                    session.add(
                        Metric(
                            ts=ts,
                            source="binance",
                            asset=symbol,
                            metric_name=name,
                            value=float(value),
                        )
                    )
            await session.commit()

    async def _evaluate(self, symbol: str, snapshot: dict[str, Any]) -> None:
        async with self._sessionmaker() as session:
            ctx = RuleContext(
                asset=symbol,
                now=datetime.now(UTC),
                payload=snapshot,
            )
            signals = await self._engine.run(session, ctx)
            await session.commit()
        if signals:
            logger.info("{}: fired {} signal(s)", symbol, len(signals))
            await self._notifier.dispatch(signals)
