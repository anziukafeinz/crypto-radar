"""Application entrypoint — wires bot, scheduler, and database together."""

from __future__ import annotations

import asyncio
import sys

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from radar import __version__
from radar.bot import build_dispatcher
from radar.config import get_settings
from radar.db.session import init_db
from radar.scheduler import build_scheduler


def configure_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
            "<level>{level: <8}</level> "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
        ),
        backtrace=True,
        diagnose=False,
    )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Crypto Radar v{} starting", __version__)

    await init_db()

    if settings.telegram_bot_token is None:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set; the bot cannot start. "
            "Copy .env.example to .env and fill it in."
        )
        return

    bot = Bot(
        token=settings.telegram_bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dispatcher = build_dispatcher()

    scheduler = build_scheduler()
    scheduler.start()

    try:
        logger.info("Bot polling start")
        await dispatcher.start_polling(bot, handle_signals=True)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot polling stopped")


def run() -> None:
    """Synchronous entrypoint exposed via Poetry script."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    run()
