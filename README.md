# Crypto Radar

Personal crypto **Derivatives Screener + Narrative Radar** with Telegram alerts.
Targeted at swing/positional traders. Multichain. 100% free data sources.

## Features (planned)

- **Derivatives Screener** — OI, funding, long/short ratio, liquidation cascades, basis, options IV, across Binance / Bybit / OKX / Deribit / Hyperliquid.
- **Narrative Radar** — sector heat scoring, narrative rotation, token unlocks, news firehose, KOL mentions (Farcaster).
- **Cross-signal alerts** — combinations like *funding overheated + narrative cooling* delivered to Telegram.
- **Daily digest** — morning summary of sector movers, unlocks, funding outliers, and top headlines.

## Architecture

```
Telegram Bot (aiogram) <---> Alert Engine <---> Scheduler (APScheduler) <---> Source Adapters (httpx)
                                  |
                                  v
                            SQLite (SQLAlchemy async)
```

Single Python process, async throughout. Designed to run on a $5/month VPS or Fly.io free tier.

## Project layout

```
src/radar/
    config.py            # pydantic-settings
    main.py              # entrypoint
    scheduler.py         # APScheduler wiring
    db/                  # SQLAlchemy async engine & models
    sources/             # Per-API adapters (binance, bybit, coingecko, ...)
    modules/
        derivatives/     # Funding / OI / Liquidation / Basis logic
        narrative/       # Sector heat / Unlocks / News
    alerts/
        engine.py        # Rule evaluation & dedup
        presets.py       # Built-in alert rules
        formatters.py    # Telegram markdown
    bot/
        handlers.py      # Telegram command handlers
```

## Quick start

### Prerequisites

- Python 3.12+
- Poetry 1.8+
- A Telegram bot token (create via [@BotFather](https://t.me/BotFather))
- Your Telegram chat ID (use [@userinfobot](https://t.me/userinfobot))

### Setup

```bash
git clone https://github.com/anziukafeinz/crypto-radar.git
cd crypto-radar
poetry install
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID
poetry run radar
```

On first run the SQLite database is auto-created at `./data/radar.db`.

### Docker

```bash
docker compose up --build
```

### Tests & lint

```bash
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src
```

## Status

| Sprint | Scope | Status |
|---|---|---|
| 0 | Skeleton + Telegram bot hello-world + SQLite | done |
| 1 | Derivatives MVP — Binance source, 4 alert presets, scheduler poll | done |
| 1.5 | Liquidation data source (Coinglass / WebSocket) | planned |
| 2 | Narrative MVP — 2 alerts + daily digest | planned |
| 3 | Cross-signal, threshold tuning per user, backtest replay | planned |

## Alert presets (Sprint 1)

| Preset | Trigger |
|---|---|
| `funding_extreme` | Funding rate > +0.05% (long) or < -0.03% (short) |
| `oi_surge` | 24h OI move > +15% with `|price%|` < 3% (squeeze setup) |
| `basis_blowout` | Annualised basis (funding × 3 × 365) outside `[-10%, +25%]` |
| `liq_cascade` | 1h long/short liq USD ≥ $50M (BTC/ETH) or $10M (other) — *scaffolded, awaiting Sprint 1.5 data source* |

## Bot commands

```
/start /help /ping /status /version
/presets               list active alert rules
/watch <SYMBOL>        add to your watchlist
/unwatch <SYMBOL>      remove from watchlist
/mute <SYMBOL>         mute alerts for a symbol
/unmute <SYMBOL>       re-enable alerts
/derivs <SYMBOL>       latest derivatives metrics from the DB
```

## License

Personal project. No license — all rights reserved.
