"""Liquidation cascade detection.

Sprint 1 ships only the rule scaffold — Binance public REST does not expose
historical liquidation data and Bybit/OKX endpoints are inconsistent across
versions. The dedicated source adapter (Coinglass or per-exchange WebSocket
``forceOrder`` stream) lands in Sprint 1.5.

When ``ctx.payload['liq_long_usd_1h']`` and ``ctx.payload['liq_short_usd_1h']``
are populated, this rule fires on cascades above the configured threshold.
"""

from __future__ import annotations

from radar.alerts.engine import AlertSignal, BaseRule, RuleContext, Severity


class LiquidationCascadeRule(BaseRule):
    """Aggregate 1h liquidation USD volume against asset-tier thresholds."""

    name = "liq_cascade"
    cooldown_minutes = 60
    dedup_bucket_minutes = 15

    major_threshold_usd: float = 50_000_000
    minor_threshold_usd: float = 10_000_000

    async def evaluate(self, ctx: RuleContext) -> AlertSignal | None:
        long_usd = ctx.payload.get("liq_long_usd_1h")
        short_usd = ctx.payload.get("liq_short_usd_1h")
        if not isinstance(long_usd, int | float) or not isinstance(short_usd, int | float):
            return None
        long_f = float(long_usd)
        short_f = float(short_usd)
        is_major = bool(ctx.payload.get("is_major"))
        threshold = self.major_threshold_usd if is_major else self.minor_threshold_usd
        if long_f >= threshold:
            side, amount = "long", long_f
        elif short_f >= threshold:
            side, amount = "short", short_f
        else:
            return None
        return AlertSignal(
            preset=self.name,
            asset=ctx.asset,
            title=f"Liquidation cascade ${amount / 1e6:.1f}M ({side})",
            body=(
                f"{side.title()} liquidations hit ${amount / 1e6:.1f}M in the last hour "
                f"(threshold ${threshold / 1e6:.0f}M)."
            ),
            severity=Severity.CRITICAL,
            payload={"side": side, "usd": amount, "threshold_usd": threshold},
        )
