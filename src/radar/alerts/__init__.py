"""Alert engine — rule evaluation, deduplication, formatting."""

from radar.alerts.engine import AlertEngine, AlertSignal, BaseRule, RuleContext, Severity
from radar.alerts.formatters import format_telegram

__all__ = [
    "AlertEngine",
    "AlertSignal",
    "BaseRule",
    "RuleContext",
    "Severity",
    "format_telegram",
]
