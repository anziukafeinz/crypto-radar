"""Application entrypoint — wires bot, scheduler, and database together."""

from __future__ import annotations

import asyncio
import sys
from contextlib import suppress

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from radar import __version__
from radar.alerts.dispatcher import TelegramNotifier
from radar.alerts.engine import AlertEngine
from radar.alerts.presets import load_default_rules
from radar.bot import build_dispatcher
from radar.config import get_settings
from radar.db.session import get_sessionmaker, init_db
from radar.modules.derivatives import (
    DerivativesPoller,
    LiquidationAggregator,
    LiquidationEvent,
    parse_universe,
)
from radar.scheduler import build_scheduler
from radar.sources.binance import Binance
from radar.sources.binance_ws import BinanceLiquidationStream
from radar.sources.bybit_ws import BybitLiquidationStream


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

    sessionmaker = get_sessionmaker()
    binance = Binance()
    engine = AlertEngine(rules=load_default_rules())
    notifier = TelegramNotifier(bot=bot, sessionmaker=sessionmaker)
    universe = parse_universe(settings.derivatives_universe)
    logger.info("Tracking {} symbols: {}", len(universe), ", ".join(universe))

    liq_aggregator = LiquidationAggregator()

    def _on_liquidation(event: LiquidationEvent) -> None:
        liq_aggregator.record(event)

    # Two liquidation feeds run in parallel — both write to the same
    # aggregator. Bybit is the primary source (Sprint 1.7) because Binance's
    # public ``forceOrder`` stream has been observed silent from many regions
    # despite REST being reachable; Binance stays a best-effort secondary.
    if settings.binance_forceorder_ws_url:
        binance_liq_stream = BinanceLiquidationStream(
            on_event=_on_liquidation,
            url=settings.binance_forceorder_ws_url,
        )
    else:
        binance_liq_stream = BinanceLiquidationStream(on_event=_on_liquidation)

    if settings.bybit_liquidation_ws_url:
        bybit_liq_stream = BybitLiquidationStream(
            on_event=_on_liquidation,
            symbols=universe,
            url=settings.bybit_liquidation_ws_url,
        )
    else:
        bybit_liq_stream = BybitLiquidationStream(
            on_event=_on_liquidation,
            symbols=universe,
        )

    poller = DerivativesPoller(
        binance=binance,
        sessionmaker=sessionmaker,
        engine=engine,
        notifier=notifier,
        universe=universe,
        liq_aggregator=liq_aggregator,
    )

    scheduler = build_scheduler(settings, poller)
    scheduler.start()

    binance_liq_task = asyncio.create_task(binance_liq_stream.run(), name="binance_liquidation_ws")
    bybit_liq_task = asyncio.create_task(bybit_liq_stream.run(), name="bybit_liquidation_ws")

    try:
        logger.info("Bot polling start")
        await dispatcher.start_polling(bot, handle_signals=True)
    finally:
        binance_liq_stream.stop()
        bybit_liq_stream.stop()
        binance_liq_task.cancel()
        bybit_liq_task.cancel()
        with suppress(asyncio.CancelledError):
            await binance_liq_task
        with suppress(asyncio.CancelledError):
            await bybit_liq_task
        scheduler.shutdown(wait=False)
        await binance.aclose()
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
