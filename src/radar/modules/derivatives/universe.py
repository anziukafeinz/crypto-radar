"""Tracked perpetual symbol universe.

Sprint 1 hard-codes the top USDT-margined perps so the poller has a sensible
default without any external lookups. Override at runtime via the
``DERIVATIVES_UNIVERSE`` env var (comma-separated, e.g. ``BTC,ETH,SOL``).
"""

from __future__ import annotations

DEFAULT_PERPETUALS: tuple[str, ...] = (
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "ADA",
    "AVAX",
    "DOGE",
    "DOT",
    "TRX",
    "LINK",
    "LTC",
    "BCH",
    "NEAR",
    "OP",
    "ARB",
    "INJ",
    "APT",
    "SUI",
    "TIA",
    "SEI",
    "RUNE",
    "ATOM",
    "ICP",
    "ETC",
    "FIL",
    "AAVE",
    "RENDER",
    "PEPE",
    "WIF",
)


def parse_universe(raw: str | None) -> list[str]:
    """Parse a comma-separated env override; fall back to defaults."""
    if not raw:
        return list(DEFAULT_PERPETUALS)
    cleaned = [chunk.strip().upper() for chunk in raw.split(",") if chunk.strip()]
    return cleaned or list(DEFAULT_PERPETUALS)


def to_binance(symbol: str) -> str:
    """Return Binance USDT-perp symbol id (e.g. ``BTC`` -> ``BTCUSDT``)."""
    return f"{symbol.upper()}USDT"


def from_binance(binance_symbol: str) -> str | None:
    """Convert a Binance USDT-perp id back to the radar bare symbol.

    ``BTCUSDT`` -> ``BTC``. ``1000PEPEUSDT`` -> ``PEPE`` (Binance prefixes
    micro-cap perps with ``1000``; the radar universe uses the bare ticker).
    Returns ``None`` for non-USDT-margined or otherwise unrecognised ids
    (e.g. ``BTCBUSD``, ``ETHUSDC``) so the caller can drop the frame.
    """
    s = binance_symbol.upper()
    if not s.endswith("USDT"):
        return None
    base = s[:-4]
    if base.startswith("1000") and len(base) > 4 and base[4:].isalpha():
        base = base[4:]
    return base or None


def is_major(symbol: str) -> bool:
    return symbol.upper() in {"BTC", "ETH"}
