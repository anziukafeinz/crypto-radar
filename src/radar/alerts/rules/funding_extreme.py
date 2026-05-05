"""Funding rate extremes (overheated long / extreme short bias)."""

from __future__ import annotations

from radar.alerts.engine import AlertSignal, BaseRule, RuleContext, Severity


class FundingExtremeRule(BaseRule):
    """Fire when the latest funding rate exits a tunable corridor."""

    name = "funding_extreme"
    cooldown_minutes = 8 * 60
    dedup_bucket_minutes = 60

    upper_threshold: float = 0.0005
    lower_threshold: float = -0.0003

    async def evaluate(self, ctx: RuleContext) -> AlertSignal | None:
        funding = ctx.payload.get("funding_rate")
        if not isinstance(funding, int | float):
            return None
        funding = float(funding)
        if funding > self.upper_threshold:
            return AlertSignal(
                preset=self.name,
                asset=ctx.asset,
                title=f"Funding {funding * 100:+.4f}% — overheated long",
                body=(
                    f"Last funding rate is {funding * 100:+.4f}% "
                    f"(threshold +{self.upper_threshold * 100:.2f}%). "
                    "Crowded long bias; watch for unwind."
                ),
                severity=Severity.HIGH,
                payload={"funding_rate": funding, "side": "long"},
            )
        if funding < self.lower_threshold:
            return AlertSignal(
                preset=self.name,
                asset=ctx.asset,
                title=f"Funding {funding * 100:+.4f}% — extreme short bias",
                body=(
                    f"Last funding rate is {funding * 100:+.4f}% "
                    f"(threshold {self.lower_threshold * 100:.2f}%). "
                    "Possible short-squeeze fuel."
                ),
                severity=Severity.HIGH,
                payload={"funding_rate": funding, "side": "short"},
            )
        return None
