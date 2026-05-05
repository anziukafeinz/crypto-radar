"""Alert preset registry.

Sprint 1 wires up four derivatives rules. Sprint 2 will append narrative rules.
"""

from __future__ import annotations

from radar.alerts.engine import BaseRule
from radar.alerts.rules import (
    BasisBlowoutRule,
    FundingExtremeRule,
    LiquidationCascadeRule,
    OISurgeRule,
)


def load_default_rules() -> list[BaseRule]:
    """Return rule instances that the engine evaluates on every poll cycle."""
    return [
        FundingExtremeRule(),
        OISurgeRule(),
        BasisBlowoutRule(),
        LiquidationCascadeRule(),
    ]
