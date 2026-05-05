"""In-memory rolling-window aggregator for force-liquidation events.

Events arrive from a streaming source (Binance ``forceOrder`` WebSocket).
The aggregator keeps the trailing ``window_seconds`` per radar symbol and
exposes per-side USD totals to the rule engine.

This deliberately stays in-memory: liquidation cascades are evaluated against
the last hour, the writer (WebSocket) and the reader (poll cycle) live in the
same process, and persisting every tick to SQLite would multiply IO with no
analytical benefit.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

LiquidationSide = Literal["long", "short"]


@dataclass(frozen=True, slots=True)
class LiquidationEvent:
    """One force-liquidation, normalised to USD on the radar symbol."""

    symbol: str
    side: LiquidationSide
    usd: float
    ts: datetime


class LiquidationAggregator:
    """Thread-safe rolling-window totals over recent liquidations."""

    def __init__(self, window_seconds: int = 3600) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._window = window_seconds
        self._buckets: defaultdict[str, deque[LiquidationEvent]] = defaultdict(deque)
        self._lock = threading.Lock()

    def record(self, event: LiquidationEvent) -> None:
        """Append an event and evict anything older than the window."""
        with self._lock:
            self._buckets[event.symbol].append(event)
            self._evict_locked(event.symbol, event.ts)

    def totals(self, symbol: str, *, now: datetime | None = None) -> tuple[float, float]:
        """Return ``(long_usd, short_usd)`` summed over the trailing window."""
        cutoff = now or datetime.now(UTC)
        with self._lock:
            self._evict_locked(symbol, cutoff)
            bucket = self._buckets.get(symbol)
            if not bucket:
                return 0.0, 0.0
            long_usd = sum(e.usd for e in bucket if e.side == "long")
            short_usd = sum(e.usd for e in bucket if e.side == "short")
        return long_usd, short_usd

    def event_count(self, symbol: str) -> int:
        """Return the number of events currently retained for ``symbol``."""
        with self._lock:
            return len(self._buckets.get(symbol, ()))

    def tracked_symbols(self) -> list[str]:
        with self._lock:
            return [s for s, b in self._buckets.items() if b]

    def _evict_locked(self, symbol: str, now: datetime) -> None:
        bucket = self._buckets.get(symbol)
        if not bucket:
            return
        cutoff = now.timestamp() - self._window
        while bucket and bucket[0].ts.timestamp() < cutoff:
            bucket.popleft()
        if not bucket:
            self._buckets.pop(symbol, None)
