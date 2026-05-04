"""Derivatives poller integration test using stub source + notifier."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "1")

from radar.alerts.engine import AlertEngine, AlertSignal
from radar.alerts.presets import load_default_rules
from radar.db.models import Alert, Base, Metric
from radar.modules.derivatives.poller import DerivativesPoller


class StubBinance:
    """Minimal in-memory replacement for :class:`radar.sources.binance.Binance`."""

    def __init__(
        self,
        *,
        funding_rate: float = 0.0001,
        mark_price: float = 50_000.0,
        index_price: float = 49_990.0,
        oi_24h_ago: float = 1_000_000.0,
        oi_now: float = 1_000_000.0,
        price_24h_ago: float = 50_000.0,
        price_now: float = 50_000.0,
    ) -> None:
        self.funding_rate = funding_rate
        self.mark_price = mark_price
        self.index_price = index_price
        self.oi_24h_ago = oi_24h_ago
        self.oi_now = oi_now
        self.price_24h_ago = price_24h_ago
        self.price_now = price_now

    async def premium_index(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "markPrice": str(self.mark_price),
            "indexPrice": str(self.index_price),
            "lastFundingRate": str(self.funding_rate),
        }

    async def open_interest_hist(
        self, symbol: str, period: str = "1h", limit: int = 24
    ) -> list[dict[str, Any]]:
        # Only first/last entries matter for the snapshot.
        rows: list[dict[str, Any]] = []
        for i in range(limit):
            value = self.oi_24h_ago if i == 0 else self.oi_now
            rows.append({"symbol": symbol, "sumOpenInterestValue": str(value), "timestamp": i})
        return rows

    async def klines(self, symbol: str, interval: str = "1h", limit: int = 24) -> list[list[Any]]:
        rows: list[list[Any]] = []
        for i in range(limit):
            close = self.price_24h_ago if i == 0 else self.price_now
            rows.append([i, "0", "0", "0", str(close), "0"])
        return rows


class StubNotifier:
    def __init__(self) -> None:
        self.dispatched: list[AlertSignal] = []

    async def dispatch(self, signals: list[AlertSignal]) -> None:
        self.dispatched.extend(signals)


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield sm
    await engine.dispose()


@pytest.mark.asyncio
async def test_poller_persists_metrics_without_firing_when_calm(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    binance = StubBinance(funding_rate=0.0001)
    notifier = StubNotifier()
    engine = AlertEngine(rules=load_default_rules())
    poller = DerivativesPoller(
        binance=binance,  # type: ignore[arg-type]
        sessionmaker=session_factory,
        engine=engine,
        notifier=notifier,  # type: ignore[arg-type]
        universe=["BTC"],
    )
    await poller.poll()

    async with session_factory() as session:
        metrics = (await session.execute(select(Metric))).scalars().all()
        alerts = (await session.execute(select(Alert))).scalars().all()
    metric_names = {m.metric_name for m in metrics}
    assert {
        "mark_price",
        "index_price",
        "funding_rate",
        "oi_now_usd",
        "oi_24h_ago_usd",
        "price_now",
        "price_24h_ago",
    } <= metric_names
    assert alerts == []
    assert notifier.dispatched == []


@pytest.mark.asyncio
async def test_poller_fires_funding_extreme_and_dispatches(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    binance = StubBinance(funding_rate=0.001)
    notifier = StubNotifier()
    engine = AlertEngine(rules=load_default_rules())
    poller = DerivativesPoller(
        binance=binance,  # type: ignore[arg-type]
        sessionmaker=session_factory,
        engine=engine,
        notifier=notifier,  # type: ignore[arg-type]
        universe=["BTC"],
    )
    await poller.poll()
    presets = {s.preset for s in notifier.dispatched}
    assert "funding_extreme" in presets
    assert "basis_blowout" in presets


@pytest.mark.asyncio
async def test_poller_fires_oi_surge_when_oi_jumps_with_flat_price(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    binance = StubBinance(
        funding_rate=0.0,
        oi_24h_ago=1_000_000.0,
        oi_now=1_300_000.0,
        price_24h_ago=50_000.0,
        price_now=50_500.0,
    )
    notifier = StubNotifier()
    engine = AlertEngine(rules=load_default_rules())
    poller = DerivativesPoller(
        binance=binance,  # type: ignore[arg-type]
        sessionmaker=session_factory,
        engine=engine,
        notifier=notifier,  # type: ignore[arg-type]
        universe=["BTC"],
    )
    await poller.poll()
    presets = {s.preset for s in notifier.dispatched}
    assert "oi_surge" in presets
