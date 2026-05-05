"""APScheduler wiring.

Sprint 0 only registers a heartbeat job. Sprint 1+ adds derivative pollers and
the daily digest cron.
"""

from __future__ import annotations

from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from radar.config import get_settings


async def heartbeat() -> None:
    """Lightweight scheduler heartbeat used during Sprint 0."""
    logger.debug("scheduler heartbeat at {}", datetime.now(UTC).isoformat())


def build_scheduler() -> AsyncIOScheduler:
    """Create the configured scheduler with default jobs."""
    settings = get_settings()
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    scheduler.add_job(
        heartbeat,
        trigger=IntervalTrigger(minutes=5),
        id="heartbeat",
        replace_existing=True,
    )

    scheduler.add_job(
        heartbeat,
        trigger=CronTrigger(hour=settings.digest_hour_local, minute=0),
        id="daily_digest_placeholder",
        replace_existing=True,
    )

    logger.info(
        "Scheduler configured (tz={}, derivatives={}m, narrative={}m, digest={:02d}:00)",
        settings.timezone,
        settings.derivatives_poll_interval_min,
        settings.narrative_poll_interval_min,
        settings.digest_hour_local,
    )
    return scheduler
