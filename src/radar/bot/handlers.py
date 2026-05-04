"""Telegram bot command handlers."""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import Dispatcher, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from radar import __version__
from radar.alerts.presets import load_default_rules
from radar.config import get_settings
from radar.db.models import Metric, Subscriber
from radar.db.session import session_scope

router = Router(name="radar")


def _is_admin(message: Message) -> bool:
    settings = get_settings()
    if settings.telegram_admin_chat_id is None:
        return True
    return message.chat.id == settings.telegram_admin_chat_id


async def _get_or_create_subscriber(session: AsyncSession, message: Message) -> Subscriber:
    result = await session.execute(select(Subscriber).where(Subscriber.chat_id == message.chat.id))
    sub = result.scalar_one_or_none()
    if sub is None:
        sub = Subscriber(
            chat_id=message.chat.id,
            name=message.from_user.full_name if message.from_user else None,
            is_admin=_is_admin(message),
        )
        session.add(sub)
        await session.flush()
        logger.info("Registered new subscriber {} (admin={})", sub.chat_id, sub.is_admin)
    return sub


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Register the chat and greet the user."""
    settings = get_settings()
    async with session_scope() as session:
        await _get_or_create_subscriber(session, message)

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
        "/status — bot status\n"
        "/version — show build version\n"
        "/presets — list active alert rules\n"
        "/watch `<SYMBOL>` — add to your watchlist\n"
        "/unwatch `<SYMBOL>` — remove from watchlist\n"
        "/mute `<SYMBOL>` — mute alerts for a symbol\n"
        "/unmute `<SYMBOL>` — re-enable alerts\n"
        "/derivs `<SYMBOL>` — latest derivatives metrics\n"
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


@router.message(Command("presets"))
async def cmd_presets(message: Message) -> None:
    rules = load_default_rules()
    if not rules:
        await message.answer("No alert presets registered.")
        return
    lines = ["*Active alert presets*"]
    for rule in rules:
        lines.append(f"- `{rule.name}` (cooldown {rule.cooldown_minutes}m)")
    await message.answer("\n".join(lines), parse_mode="Markdown")


def _parse_symbol(command: CommandObject) -> str | None:
    if not command.args:
        return None
    return command.args.strip().split()[0].upper() if command.args.strip() else None


@router.message(Command("watch"))
async def cmd_watch(message: Message, command: CommandObject) -> None:
    symbol = _parse_symbol(command)
    if symbol is None:
        await message.answer("Usage: `/watch BTC`", parse_mode="Markdown")
        return
    async with session_scope() as session:
        sub = await _get_or_create_subscriber(session, message)
        if symbol not in sub.watchlist:
            sub.watchlist = [*sub.watchlist, symbol]
    await message.answer(f"Watching `{symbol}`.", parse_mode="Markdown")


@router.message(Command("unwatch"))
async def cmd_unwatch(message: Message, command: CommandObject) -> None:
    symbol = _parse_symbol(command)
    if symbol is None:
        await message.answer("Usage: `/unwatch BTC`", parse_mode="Markdown")
        return
    async with session_scope() as session:
        sub = await _get_or_create_subscriber(session, message)
        sub.watchlist = [s for s in sub.watchlist if s != symbol]
    await message.answer(f"Unwatched `{symbol}`.", parse_mode="Markdown")


@router.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject) -> None:
    symbol = _parse_symbol(command)
    if symbol is None:
        await message.answer("Usage: `/mute BTC`", parse_mode="Markdown")
        return
    async with session_scope() as session:
        sub = await _get_or_create_subscriber(session, message)
        if symbol not in sub.muted_assets:
            sub.muted_assets = [*sub.muted_assets, symbol]
    await message.answer(f"Muted `{symbol}`.", parse_mode="Markdown")


@router.message(Command("unmute"))
async def cmd_unmute(message: Message, command: CommandObject) -> None:
    symbol = _parse_symbol(command)
    if symbol is None:
        await message.answer("Usage: `/unmute BTC`", parse_mode="Markdown")
        return
    async with session_scope() as session:
        sub = await _get_or_create_subscriber(session, message)
        sub.muted_assets = [s for s in sub.muted_assets if s != symbol]
    await message.answer(f"Unmuted `{symbol}`.", parse_mode="Markdown")


@router.message(Command("derivs"))
async def cmd_derivs(message: Message, command: CommandObject) -> None:
    symbol = _parse_symbol(command)
    if symbol is None:
        await message.answer("Usage: `/derivs BTC`", parse_mode="Markdown")
        return
    async with session_scope() as session:
        result = await session.execute(
            select(Metric).where(Metric.asset == symbol).order_by(Metric.ts.desc()).limit(50)
        )
        metrics = list(result.scalars().all())
    if not metrics:
        await message.answer(
            f"No data for `{symbol}` yet. Wait for the next poll cycle.",
            parse_mode="Markdown",
        )
        return
    latest: dict[str, Metric] = {}
    for m in metrics:
        latest.setdefault(m.metric_name, m)
    lines = [f"*{symbol}* — latest derivatives"]
    funding = latest.get("funding_rate")
    mark = latest.get("mark_price")
    index = latest.get("index_price")
    oi_now = latest.get("oi_now_usd")
    oi_24 = latest.get("oi_24h_ago_usd")
    price_now = latest.get("price_now")
    price_24 = latest.get("price_24h_ago")
    if mark is not None:
        lines.append(f"mark: `{mark.value:,.4f}`")
    if index is not None:
        lines.append(f"index: `{index.value:,.4f}`")
    if funding is not None:
        lines.append(f"funding: `{funding.value * 100:+.4f}%`")
    if oi_now is not None and oi_24 is not None and oi_24.value > 0:
        oi_pct = (oi_now.value - oi_24.value) / oi_24.value * 100
        lines.append(f"OI 24h Δ: `{oi_pct:+.2f}%` (now ${oi_now.value / 1e6:,.1f}M)")
    if price_now is not None and price_24 is not None and price_24.value > 0:
        price_pct = (price_now.value - price_24.value) / price_24.value * 100
        lines.append(f"price 24h Δ: `{price_pct:+.2f}%`")
    await message.answer("\n".join(lines), parse_mode="Markdown")


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher
