"""Render :class:`AlertSignal` instances into channel-specific payloads."""

from __future__ import annotations

from radar.alerts.engine import AlertSignal, Severity

_SEVERITY_PREFIX: dict[Severity, str] = {
    Severity.INFO: "[INFO]",
    Severity.HIGH: "[HIGH]",
    Severity.CRITICAL: "[CRITICAL]",
}


def format_telegram(signal: AlertSignal) -> str:
    """Compose a Telegram-friendly Markdown message from an alert signal."""
    prefix = _SEVERITY_PREFIX.get(signal.severity, "[INFO]")
    header = f"{prefix} *{signal.preset}* — `{signal.asset}`"
    title = f"*{signal.title}*"
    return f"{header}\n{title}\n\n{signal.body}"
