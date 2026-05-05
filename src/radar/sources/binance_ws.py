"""Binance USD-M Futures public WebSocket: ``forceOrder`` (liquidation) stream.

Connects to ``wss://fstream.binance.com/ws/!forceOrder@arr`` (the all-symbol
liquidation feed), parses each frame into a
:class:`~radar.modules.derivatives.liq_aggregator.LiquidationEvent`, and
forwards it to a callback. Reconnects with exponential backoff on disconnect.

Public stream — no auth. Note that ``fapi.binance.com`` is geo-blocked from
some hosting regions; the listener degrades gracefully (logs the failure,
keeps retrying) so the rest of the bot keeps working even when this stream
is unreachable.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import websockets
from loguru import logger

from radar.modules.derivatives.liq_aggregator import (
    LiquidationEvent,
    LiquidationSide,
)
from radar.modules.derivatives.universe import from_binance

EventCallback = Callable[[LiquidationEvent], Awaitable[None] | None]

DEFAULT_FORCEORDER_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"


class BinanceLiquidationStream:
    """Long-lived consumer of Binance's all-symbol ``forceOrder`` stream."""

    def __init__(
        self,
        on_event: EventCallback,
        *,
        url: str = DEFAULT_FORCEORDER_URL,
        reconnect_initial: float = 1.0,
        reconnect_max: float = 60.0,
        ping_interval: float = 20.0,
    ) -> None:
        self._on_event = on_event
        self._url = url
        self._reconnect_initial = reconnect_initial
        self._reconnect_max = reconnect_max
        self._ping_interval = ping_interval
        self._stopped = asyncio.Event()

    def stop(self) -> None:
        self._stopped.set()

    async def run(self) -> None:
        """Connect, consume, reconnect on failure until :meth:`stop` is called."""
        backoff = self._reconnect_initial
        while not self._stopped.is_set():
            try:
                async with websockets.connect(
                    self._url,
                    ping_interval=self._ping_interval,
                    open_timeout=10,
                ) as ws:
                    logger.info("binance_ws: connected to {}", self._url)
                    backoff = self._reconnect_initial
                    await self._consume(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "binance_ws: disconnected ({}); reconnecting in {:.1f}s",
                    exc,
                    backoff,
                )
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=backoff)
                except TimeoutError:
                    pass
                backoff = min(self._reconnect_max, backoff * 2)
        logger.info("binance_ws: stopped")

    async def _consume(self, ws: Any) -> None:
        async for raw in ws:
            if self._stopped.is_set():
                break
            event = parse_force_order(raw)
            if event is None:
                continue
            try:
                result = self._on_event(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("binance_ws: callback failed for {}", event.symbol)


def parse_force_order(raw: str | bytes) -> LiquidationEvent | None:
    """Parse one ``forceOrder`` frame into a :class:`LiquidationEvent` (or ``None``).

    Side mapping follows Binance's order side, not the position side:

    - ``"S": "SELL"`` — the matching engine is selling to close a **long**
      position, so the event counts as a long liquidation.
    - ``"S": "BUY"`` — closing a short position, counts as a short liquidation.
    """
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("binance_ws: malformed JSON frame")
        return None

    if not isinstance(payload, dict) or payload.get("e") != "forceOrder":
        return None
    order = payload.get("o")
    if not isinstance(order, dict):
        return None
    binance_symbol = order.get("s")
    if not isinstance(binance_symbol, str):
        return None

    side_raw = order.get("S")
    side: LiquidationSide
    if side_raw == "SELL":
        side = "long"
    elif side_raw == "BUY":
        side = "short"
    else:
        return None

    try:
        filled_qty = float(order.get("z") or order.get("q") or 0)
        avg_price = float(order.get("ap") or order.get("p") or 0)
    except (TypeError, ValueError):
        return None
    usd = filled_qty * avg_price
    if usd <= 0:
        return None

    ts_ms = order.get("T") or payload.get("E")
    if isinstance(ts_ms, int | float):
        ts = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
    else:
        ts = datetime.now(UTC)

    symbol = from_binance(binance_symbol)
    if symbol is None:
        return None

    return LiquidationEvent(symbol=symbol, side=side, usd=usd, ts=ts)
