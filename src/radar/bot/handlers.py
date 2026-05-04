"""Telegram bot command handlers (Sprint 0 — hello world)."""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger
from sqlalchemy import select

from radar import __version__
from radar.config import get_settings
from radar.db.models import Subscriber
from radar.db.session import session_scope

router = Router(name="radar")


def _is_admin(message: Message) -> bool:
    settings = get_settings()
    if settings.telegram_admin_chat_id is None:
        return True
    return message.chat.id == settings.telegram_admin_chat_id


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Register the chat and greet the user."""
    settings = get_settings()
    is_admin = _is_admin(message)
    async with session_scope() as session:
        existing = await session.execute(
            select(Subscriber).where(Subscriber.chat_id == message.chat.id)
        )
        subscriber = existing.scalar_one_or_none()
        if subscriber is None:
            session.add(
                Subscriber(
                    chat_id=message.chat.id,
                    name=message.from_user.full_name if message.from_user else None,
                    is_admin=is_admin,
                )
            )
            logger.info("Registered new subscriber {} (admin={})", message.chat.id, is_admin)

    lines = [
        f"*Crypto Radar* v{__version__}",
        "",
        "Personal Derivatives Screener + Narrative Radar.",
        f"Timezone: `{settings.timezone}`",
        "",
        "Try /help for commands.",
    ]
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    body = (
        "*Available commands*\n"
        "/start — register & greet\n"
        "/help — this message\n"
        "/ping — liveness check\n"
        "/status — bot status & uptime\n"
        "/version — show build version\n"
        "\n"
        "_Watchlist & alert presets land in Sprint 1._"
    )
    await message.answer(body, parse_mode="Markdown")


@router.message(Command("ping"))
async def cmd_ping(message: Message) -> None:
    await message.answer("pong")


@router.message(Command("version"))
async def cmd_version(message: Message) -> None:
    await message.answer(f"crypto-radar v{__version__}")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    settings = get_settings()
    if not _is_admin(message):
        await message.answer("Admin only.")
        return
    now = datetime.now(UTC).isoformat(timespec="seconds")
    body = (
        "*Status*\n"
        f"version: `{__version__}`\n"
        f"now (UTC): `{now}`\n"
        f"derivatives_poll: every `{settings.derivatives_poll_interval_min}` min\n"
        f"narrative_poll: every `{settings.narrative_poll_interval_min}` min\n"
        f"daily_digest: `{settings.digest_hour_local:02d}:00 {settings.timezone}`"
    )
    await message.answer(body, parse_mode="Markdown")


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher
