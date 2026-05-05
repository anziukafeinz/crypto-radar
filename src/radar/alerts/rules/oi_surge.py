"""OI surge with sideways price — classic squeeze setup."""

from __future__ import annotations

from radar.alerts.engine import AlertSignal, BaseRule, RuleContext, Severity


class OISurgeRule(BaseRule):
    """Fire when 24h open interest jumps while price barely moves."""

    name = "oi_surge"
    cooldown_minutes = 4 * 60
    dedup_bucket_minutes = 60

    oi_pct_threshold: float = 15.0
    price_abs_pct_threshold: float = 3.0

    async def evaluate(self, ctx: RuleContext) -> AlertSignal | None:
        oi_now = ctx.payload.get("oi_now_usd")
        oi_24h = ctx.payload.get("oi_24h_ago_usd")
        price_now = ctx.payload.get("price_now")
        price_24h = ctx.payload.get("price_24h_ago")
        if not all(isinstance(v, int | float) for v in (oi_now, oi_24h, price_now, price_24h)):
            return None
        oi_now_f = float(oi_now)  # type: ignore[arg-type]
        oi_24h_f = float(oi_24h)  # type: ignore[arg-type]
        price_now_f = float(price_now)  # type: ignore[arg-type]
        price_24h_f = float(price_24h)  # type: ignore[arg-type]
        if oi_24h_f <= 0 or price_24h_f <= 0:
            return None
        oi_change_pct = (oi_now_f - oi_24h_f) / oi_24h_f * 100
        price_change_pct = (price_now_f - price_24h_f) / price_24h_f * 100
        if (
            oi_change_pct > self.oi_pct_threshold
            and abs(price_change_pct) < self.price_abs_pct_threshold
        ):
            return AlertSignal(
                preset=self.name,
                asset=ctx.asset,
                title=f"OI {oi_change_pct:+.1f}% (24h) · price {price_change_pct:+.2f}%",
                body=(
                    f"Open interest moved {oi_change_pct:+.1f}% in 24h while price barely "
                    f"shifted ({price_change_pct:+.2f}%). Squeeze setup forming."
                ),
                severity=Severity.HIGH,
                payload={
                    "oi_change_pct": oi_change_pct,
                    "price_change_pct": price_change_pct,
                    "oi_now_usd": oi_now_f,
                    "oi_24h_ago_usd": oi_24h_f,
                },
            )
        return None
