"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Float, Index, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base."""


class Subscriber(Base):
    """A Telegram chat that receives alerts."""

    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(128), default=None)
    is_admin: Mapped[bool] = mapped_column(default=False)
    enabled: Mapped[bool] = mapped_column(default=True)
    threshold_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    muted_assets: Mapped[list[str]] = mapped_column(JSON, default=list)
    watchlist: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Asset(Base):
    """Tracked asset metadata."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(128), default=None)
    coingecko_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    mcap_rank: Mapped[int | None] = mapped_column(default=None)
    categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Metric(Base):
    """Time-series storage for any (source, asset, metric_name) tuple."""

    __tablename__ = "metrics"
    __table_args__ = (
        Index("ix_metrics_lookup", "asset", "metric_name", "ts"),
        Index("ix_metrics_source", "source", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(32))
    asset: Mapped[str] = mapped_column(String(32))
    metric_name: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


class Alert(Base):
    """Persisted alert event (for dedup, history, audit)."""

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("preset", "asset", "fingerprint", name="uq_alert_dedup"),
        Index("ix_alerts_recent", "preset", "asset", "fired_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    preset: Mapped[str] = mapped_column(String(64))
    asset: Mapped[str] = mapped_column(String(32))
    fingerprint: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(String(2048))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fired_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
