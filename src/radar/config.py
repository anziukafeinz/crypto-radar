"""Application settings loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    log_level: str = Field(default="INFO")
    database_url: str = Field(default="sqlite+aiosqlite:///./data/radar.db")
    timezone: str = Field(default="Asia/Jakarta")

    telegram_bot_token: SecretStr | None = Field(default=None)
    telegram_admin_chat_id: int | None = Field(default=None)

    binance_api_key: SecretStr | None = Field(default=None)
    binance_api_secret: SecretStr | None = Field(default=None)
    bybit_api_key: SecretStr | None = Field(default=None)
    bybit_api_secret: SecretStr | None = Field(default=None)
    okx_api_key: SecretStr | None = Field(default=None)
    okx_api_secret: SecretStr | None = Field(default=None)
    okx_api_passphrase: SecretStr | None = Field(default=None)

    coingecko_api_key: SecretStr | None = Field(default=None)
    lunarcrush_api_key: SecretStr | None = Field(default=None)
    github_token: SecretStr | None = Field(default=None)
    neynar_api_key: SecretStr | None = Field(default=None)

    derivatives_poll_interval_min: int = Field(default=15)
    narrative_poll_interval_min: int = Field(default=60)
    digest_hour_local: int = Field(default=7)

    derivatives_universe: str | None = Field(default=None)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached settings accessor."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
