"""Concrete alert rules. Sprint 1 ships derivatives presets."""

from radar.alerts.rules.basis_blowout import BasisBlowoutRule
from radar.alerts.rules.funding_extreme import FundingExtremeRule
from radar.alerts.rules.liq_cascade import LiquidationCascadeRule
from radar.alerts.rules.oi_surge import OISurgeRule

__all__ = [
    "BasisBlowoutRule",
    "FundingExtremeRule",
    "LiquidationCascadeRule",
    "OISurgeRule",
]
