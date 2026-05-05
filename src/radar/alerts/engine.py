"""Rule-based alert engine.

Sprint 0 ships the abstract scaffolding so later sprints can plug rules in
without touching the dispatch / dedup / persistence machinery.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from radar.db.models import Alert


class Severity(StrEnum):
    """How loud an alert should be."""

    INFO = "info"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(slots=True, frozen=True)
class RuleContext:
    """Anything a rule needs to evaluate against the latest data."""

    asset: str
    now: datetime
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AlertSignal:
    """A rule's verdict for a given context."""

    preset: str
    asset: str
    title: str
    body: str
    severity: Severity = Severity.INFO
    payload: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self, bucket_minutes: int = 15) -> str:
        """Stable hash used for deduplication within a time bucket."""
        bucket = datetime.now(UTC).replace(second=0, microsecond=0)
        bucket = bucket - timedelta(minutes=bucket.minute % max(bucket_minutes, 1))
        material = json.dumps(
            {
                "preset": self.preset,
                "asset": self.asset,
                "bucket": bucket.isoformat(timespec="minutes"),
            },
            sort_keys=True,
        )
        return hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]


class BaseRule(ABC):
    """Implement this once per alert preset."""

    name: str = "base"
    cooldown_minutes: int = 30
    dedup_bucket_minutes: int = 15

    @abstractmethod
    async def evaluate(self, ctx: RuleContext) -> AlertSignal | None:
        """Return an AlertSignal when the rule fires, otherwise None."""


class AlertEngine:
    """Evaluate rules, dedup against history, persist firings."""

    def __init__(self, rules: list[BaseRule]) -> None:
        self.rules = rules

    async def run(self, session: AsyncSession, ctx: RuleContext) -> list[AlertSignal]:
        fired: list[AlertSignal] = []
        for rule in self.rules:
            try:
                signal = await rule.evaluate(ctx)
            except Exception as exc:
                logger.exception("Rule {} crashed on {}: {}", rule.name, ctx.asset, exc)
                continue
            if signal is None:
                continue
            if await self._is_duplicate(session, rule, signal):
                logger.debug("Suppressed duplicate {} for {}", signal.preset, signal.asset)
                continue
            await self._persist(session, rule, signal)
            fired.append(signal)
        return fired

    async def _is_duplicate(
        self, session: AsyncSession, rule: BaseRule, signal: AlertSignal
    ) -> bool:
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=rule.cooldown_minutes)
        stmt = (
            select(Alert)
            .where(
                Alert.preset == signal.preset,
                Alert.asset == signal.asset,
                Alert.fired_at >= cutoff,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _persist(self, session: AsyncSession, rule: BaseRule, signal: AlertSignal) -> None:
        record = Alert(
            preset=signal.preset,
            asset=signal.asset,
            fingerprint=signal.fingerprint(rule.dedup_bucket_minutes),
            severity=signal.severity.value,
            title=signal.title,
            body=signal.body,
            payload=signal.payload,
        )
        session.add(record)
        await session.flush()
