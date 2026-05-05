"""Bybit USDT-perpetual public WebSocket: ``allLiquidation`` stream.

Connects to ``wss://stream.bybit.com/v5/public/linear``, subscribes to
``allLiquidation.{symbol}USDT`` for each tracked symbol, parses every
liquidation in each frame into a
:class:`~radar.modules.derivatives.liq_aggregator.LiquidationEvent`, and
forwards it to a callback. Reconnects with exponential backoff on disconnect.

Public stream — no auth. Bybit pushes one snapshot per 500 ms (vs Binance's
1 s "largest only" throttle), so volume is comparable to or higher than the
Binance ``forceOrder`` stream when both work, and Bybit has been observed to
deliver events from regions where Binance's stream is silent. Used as the
primary liquidation source from Sprint 1.7 onwards; Binance remains a
best-effort secondary source.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

import websockets
from loguru import logger

from radar.modules.derivatives.liq_aggregator import (
    LiquidationEvent,
    LiquidationSide,
)
from radar.modules.derivatives.universe import from_bybit, to_bybit

EventCallback = Callable[[LiquidationEvent], Awaitable[None] | None]

DEFAULT_LIQUIDATION_URL = "wss://stream.bybit.com/v5/public/linear"
SUBSCRIBE_BATCH_SIZE = 10
PING_INTERVAL_SEC = 20.0


class BybitLiquidationStream:
    """Long-lived consumer of Bybit's ``allLiquidation.{symbol}`` topics."""

    def __init__(
        self,
        on_event: EventCallback,
        symbols: Iterable[str],
        *,
        url: str = DEFAULT_LIQUIDATION_URL,
        reconnect_initial: float = 1.0,
        reconnect_max: float = 60.0,
        ping_interval: float = PING_INTERVAL_SEC,
    ) -> None:
        # Pre-compute Bybit-formatted symbols once so reconnects re-subscribe
        # to the same topics without recomputing the prefix overrides.
        self._on_event = on_event
        self._symbols: list[str] = [to_bybit(s) for s in symbols]
        self._url = url
        self._reconnect_initial = reconnect_initial
        self._reconnect_max = reconnect_max
        self._ping_interval = ping_interval
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    async def run(self) -> None:
        """Connect, subscribe, consume, reconnect on failure until stopped."""
        if not self._symbols:
            logger.warning("bybit_ws: no symbols to subscribe; idling")
            await self._stopped.wait()
            return

        backoff = self._reconnect_initial
        while not self._stopped.is_set():
            try:
                async with websockets.connect(
                    self._url,
                    open_timeout=10,
                    # Bybit prefers the app-level ``{"op":"ping"}`` heartbeat
                    # over WebSocket protocol pings; disable the library's
                    # auto-ping and run our own ping loop in ``_consume``.
                    ping_interval=None,
                ) as ws:
                    logger.info("bybit_ws: connected to {}", self._url)
                    await self._subscribe(ws)
                    backoff = self._reconnect_initial
                    await self._consume(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "bybit_ws: disconnected ({}); reconnecting in {:.1f}s",
                    exc,
                    backoff,
                )
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=backoff)
                except TimeoutError:
                    pass
                backoff = min(self._reconnect_max, backoff * 2)
        logger.info("bybit_ws: stopped")

    async def _subscribe(self, ws: Any) -> None:
        topics = [f"allLiquidation.{s}" for s in self._symbols]
        for i in range(0, len(topics), SUBSCRIBE_BATCH_SIZE):
            batch = topics[i : i + SUBSCRIBE_BATCH_SIZE]
            await ws.send(json.dumps({"op": "subscribe", "args": batch}))
        logger.info("bybit_ws: subscribed to {} liquidation topics", len(topics))

    async def _consume(self, ws: Any) -> None:
        ping_task = asyncio.create_task(self._ping_loop(ws), name="bybit_ws_ping")
        try:
            async for raw in ws:
                if self._stopped.is_set():
                    break
                events = parse_all_liquidation(raw)
                for event in events:
                    try:
                        result = self._on_event(event)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception:
                        logger.exception("bybit_ws: callback failed for {}", event.symbol)
        finally:
            ping_task.cancel()
            with suppress(asyncio.CancelledError):
                await ping_task

    async def _ping_loop(self, ws: Any) -> None:
        try:
            while not self._stopped.is_set():
                await asyncio.sleep(self._ping_interval)
                await ws.send(json.dumps({"op": "ping"}))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("bybit_ws: ping loop ended (connection likely closed)")


def parse_all_liquidation(raw: str | bytes) -> list[LiquidationEvent]:
    """Parse one ``allLiquidation`` frame into zero or more events.

    Bybit ships an array of liquidations per frame and reports the *liquidated
    position* side directly: ``"S": "Buy"`` means a **long** position was
    liquidated, ``"S": "Sell"`` means a **short** was. This is the inverse of
    Binance's mapping, which reports the matching engine's order side.

    Non-``allLiquidation.*`` frames (subscribe acks, pong replies, ticker
    snapshots, etc.) and unknown sides are dropped silently.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("bybit_ws: malformed JSON frame")
        return []

    if not isinstance(payload, dict):
        return []
    topic = payload.get("topic")
    if not isinstance(topic, str) or not topic.startswith("allLiquidation."):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []

    events: list[LiquidationEvent] = []
    for item in data:
        event = _parse_one(item, fallback_ts_ms=payload.get("ts"))
        if event is not None:
            events.append(event)
    return events


def _parse_one(item: object, *, fallback_ts_ms: object) -> LiquidationEvent | None:
    if not isinstance(item, dict):
        return None
    bybit_symbol = item.get("s")
    if not isinstance(bybit_symbol, str):
        return None

    side_raw = item.get("S")
    side: LiquidationSide
    if side_raw == "Buy":
        side = "long"
    elif side_raw == "Sell":
        side = "short"
    else:
        return None

    try:
        qty = float(item.get("v") or 0)
        price = float(item.get("p") or 0)
    except (TypeError, ValueError):
        return None
    usd = qty * price
    if usd <= 0:
        return None

    ts_ms = item.get("T") or fallback_ts_ms
    if isinstance(ts_ms, int | float):
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
    else:
        ts = datetime.now(UTC)

    symbol = from_bybit(bybit_symbol)
    if symbol is None:
        return None

    return LiquidationEvent(symbol=symbol, side=side, usd=usd, ts=ts)
