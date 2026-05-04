"""APScheduler wiring."""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

from radar.config import Settings
from radar.modules.derivatives import DerivativesPoller


def build_scheduler(settings: Settings, poller: DerivativesPoller) -> AsyncIOScheduler:
    """Create the scheduler with the derivatives poll job registered."""
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    scheduler.add_job(
        poller.poll,
        trigger=IntervalTrigger(minutes=settings.derivatives_poll_interval_min),
        id="derivatives_poll",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=settings.derivatives_poll_interval_min * 60,
    )

    logger.info(
        "Scheduler configured (tz={}, derivatives every {}m, narrative every {}m, digest at {:02d}:00)",
        settings.timezone,
        settings.derivatives_poll_interval_min,
        settings.narrative_poll_interval_min,
        settings.digest_hour_local,
    )
    return scheduler
