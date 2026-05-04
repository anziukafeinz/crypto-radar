"""Send fired alert signals to enabled Telegram subscribers."""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from radar.alerts.engine import AlertSignal
from radar.alerts.formatters import format_telegram
from radar.db.models import Alert, Subscriber


class TelegramNotifier:
    """Fan out alert signals to every enabled subscriber via Telegram."""

    def __init__(self, bot: Bot, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._bot = bot
        self._sessionmaker = sessionmaker

    async def dispatch(self, signals: list[AlertSignal]) -> None:
        if not signals:
            return
        async with self._sessionmaker() as session:
            stmt = select(Subscriber).where(Subscriber.enabled.is_(True))
            result = await session.execute(stmt)
            subscribers = list(result.scalars().all())
        if not subscribers:
            logger.warning("No enabled subscribers; {} signal(s) suppressed.", len(signals))
            return
        for signal in signals:
            text = format_telegram(signal)
            for sub in subscribers:
                if signal.asset.upper() in {a.upper() for a in sub.muted_assets}:
                    continue
                try:
                    await self._bot.send_message(sub.chat_id, text, parse_mode="Markdown")
                except TelegramAPIError as exc:
                    logger.warning(
                        "Telegram delivery failed for chat {} preset {}: {}",
                        sub.chat_id,
                        signal.preset,
                        exc,
                    )
            await self._mark_delivered(signal)

    async def _mark_delivered(self, signal: AlertSignal) -> None:
        async with self._sessionmaker() as session:
            stmt = (
                select(Alert)
                .where(
                    Alert.preset == signal.preset,
                    Alert.asset == signal.asset,
                    Alert.delivered_at.is_(None),
                )
                .order_by(Alert.fired_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is not None:
                row.delivered_at = datetime.now(UTC).replace(tzinfo=None)
                await session.commit()
