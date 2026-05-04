"""Annualized basis (funding-derived) outside an arbitrage corridor."""

from __future__ import annotations

from radar.alerts.engine import AlertSignal, BaseRule, RuleContext, Severity

FUNDING_INTERVALS_PER_DAY = 3
DAYS_PER_YEAR = 365


class BasisBlowoutRule(BaseRule):
    """Annualized basis ≈ funding * 3 * 365.

    Triggers on rich premium (cash-and-carry) or deep discount (inverse).
    """

    name = "basis_blowout"
    cooldown_minutes = 8 * 60
    dedup_bucket_minutes = 60

    upper_threshold: float = 0.25
    lower_threshold: float = -0.10

    async def evaluate(self, ctx: RuleContext) -> AlertSignal | None:
        funding = ctx.payload.get("funding_rate")
        if not isinstance(funding, int | float):
            return None
        funding = float(funding)
        annualized = funding * FUNDING_INTERVALS_PER_DAY * DAYS_PER_YEAR
        if annualized > self.upper_threshold or annualized < self.lower_threshold:
            direction = "premium" if annualized > 0 else "discount"
            return AlertSignal(
                preset=self.name,
                asset=ctx.asset,
                title=f"Basis {annualized * 100:+.1f}% annualized — {direction}",
                body=(
                    f"Annualized basis (funding-derived) is {annualized * 100:+.1f}%. "
                    "Cash-and-carry / inverse arbitrage zone."
                ),
                severity=Severity.INFO,
                payload={
                    "basis_annualized": annualized,
                    "funding_rate": funding,
                },
            )
        return None
