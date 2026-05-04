"""Smoke tests covering the Sprint 0 skeleton."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from radar import __version__
from radar.alerts.engine import AlertEngine, AlertSignal, BaseRule, RuleContext, Severity
from radar.alerts.formatters import format_telegram
from radar.alerts.presets import load_default_rules
from radar.config import get_settings
from radar.db.models import Alert, Subscriber


def test_version_string() -> None:
    assert __version__.count(".") == 2


def test_settings_defaults() -> None:
    settings = get_settings()
    assert settings.derivatives_poll_interval_min > 0
    assert settings.narrative_poll_interval_min > 0
    assert 0 <= settings.digest_hour_local <= 23


def test_load_default_rules_empty_in_sprint_0() -> None:
    assert load_default_rules() == []


def test_format_telegram_renders_severity_and_asset() -> None:
    signal = AlertSignal(
        preset="funding_extreme",
        asset="BTCUSDT",
        title="Funding +0.07% for 8h",
        body="Crowded long detected.",
        severity=Severity.HIGH,
    )
    rendered = format_telegram(signal)
    assert "[HIGH]" in rendered
    assert "funding_extreme" in rendered
    assert "BTCUSDT" in rendered
    assert "Crowded long detected." in rendered


def test_alert_signal_fingerprint_is_stable() -> None:
    signal = AlertSignal(preset="x", asset="ETH", title="t", body="b")
    assert signal.fingerprint() == signal.fingerprint()


@pytest.mark.asyncio
async def test_subscriber_round_trip(session: AsyncSession) -> None:
    session.add(Subscriber(chat_id=42, name="Tester", is_admin=True))
    await session.commit()
    result = await session.execute(select(Subscriber).where(Subscriber.chat_id == 42))
    sub = result.scalar_one()
    assert sub.is_admin is True
    assert sub.muted_assets == []


class _AlwaysFires(BaseRule):
    name = "always"
    cooldown_minutes = 0

    async def evaluate(self, ctx: RuleContext) -> AlertSignal | None:
        return AlertSignal(
            preset="always",
            asset=ctx.asset,
            title="ping",
            body="pong",
            severity=Severity.INFO,
        )


@pytest.mark.asyncio
async def test_alert_engine_persists_signals(session: AsyncSession) -> None:
    engine = AlertEngine(rules=[_AlwaysFires()])
    ctx = RuleContext(asset="BTC", now=datetime.now(UTC))
    fired = await engine.run(session, ctx)
    assert len(fired) == 1
    await session.commit()
    result = await session.execute(select(Alert))
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].asset == "BTC"


@pytest.mark.asyncio
async def test_alert_engine_dedupes_within_cooldown(session: AsyncSession) -> None:
    class _CooldownRule(_AlwaysFires):
        cooldown_minutes = 30

    engine = AlertEngine(rules=[_CooldownRule()])
    ctx = RuleContext(asset="ETH", now=datetime.now(UTC))
    first = await engine.run(session, ctx)
    await session.commit()
    second = await engine.run(session, ctx)
    await session.commit()
    assert len(first) == 1
    assert len(second) == 0
