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
| 1.5 | Liquidation data source — Binance `forceOrder` WebSocket + 1h aggregator | done |
| 1.6 | `BINANCE_FORCEORDER_WS_URL` override + `radar-tune` calibration helper | done |
| 1.7 | Bybit `allLiquidation` primary source (Binance silent in many regions) | done |
| 2 | Narrative MVP — 2 alerts + daily digest | planned |
| 3 | Cross-signal, threshold tuning per user, backtest replay | planned |

## Alert presets (Sprint 1)

| Preset | Trigger |
|---|---|
| `funding_extreme` | Funding rate > +0.05% (long) or < -0.03% (short) |
| `oi_surge` | 24h OI move > +15% with `|price%|` < 3% (squeeze setup) |
| `basis_blowout` | Annualised basis (funding × 3 × 365) outside `[-10%, +25%]` |
| `liq_cascade` | 1h long/short liq USD ≥ $50M (BTC/ETH) or $10M (other) — fed by Bybit + Binance liquidation WebSockets |

## Liquidation streams (Sprint 1.5 + 1.7)

The `liq_cascade` rule is backed by **two** public WebSocket feeds that both
write into the same in-memory `LiquidationAggregator` (rolling 1h window per
radar symbol):

- **Bybit** `wss://stream.bybit.com/v5/public/linear` — primary. The bot
  subscribes to `allLiquidation.{symbol}USDT` for every symbol in the
  universe at boot. 500 ms push frequency, no per-symbol throttle. Reaches
  more regions reliably than the Binance equivalent.
- **Binance** `wss://fstream.binance.com/ws/!forceOrder@arr` — best-effort
  secondary. One all-symbol stream. The Binance docs only push the
  *largest* liquidation per symbol per second, and the stream has been
  observed silent from VPS/residential IPs that have no trouble with the
  REST API. Treat it as a bonus when it works.

Both streams parse into `LiquidationEvent`s and feed the aggregator without
double-counting (each exchange has its own liquidations). Combined totals are
merged into the next derivatives poll snapshot as
`liq_long_usd_1h` / `liq_short_usd_1h`, persisted alongside the existing 7
metrics, and exposed via `/liq <SYMBOL>`.

Both streams auto-reconnect with exponential backoff. If either endpoint is
unreachable, the rest of the bot keeps running — its contribution to the
aggregator simply stays at `$0`.

## Tuning `liq_cascade` thresholds (Sprint 1.6 + 1.7)

The default `liq_cascade` cutoffs (`$50M` major / `$10M` minor) are first
guesses — neither exchange exposes historical liquidation data via REST, so
calibration has to happen live. The `radar-tune` helper observes the same
Bybit + Binance feed mix the bot uses, samples the rolling 1h totals, and
prints percentile recommendations:

```bash
poetry run radar-tune --minutes 60 --sample-interval-sec 60
```

Output is a per-class `p90 / p95 / p99` table plus suggested replacement
values for `LiquidationCascadeRule.major_threshold_usd` and
`minor_threshold_usd`. Edit `src/radar/alerts/rules/liq_cascade.py` to
apply them and restart the bot. Set `BYBIT_LIQUIDATION_WS_URL` /
`BINANCE_FORCEORDER_WS_URL` (or `--bybit-url` / `--binance-url`) if you
need to point at a proxy.

## Bot commands

```
/start /help /ping /status /version
/presets               list active alert rules
/watch <SYMBOL>        add to your watchlist
/unwatch <SYMBOL>      remove from watchlist
/mute <SYMBOL>         mute alerts for a symbol
/unmute <SYMBOL>       re-enable alerts
/derivs <SYMBOL>       latest derivatives metrics from the DB
/liq <SYMBOL>          last 1h liquidation totals
```

## License

Personal project. No license — all rights reserved.
