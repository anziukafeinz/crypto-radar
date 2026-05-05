"""Unit tests for derivatives alert rules."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from radar.alerts.engine import RuleContext, Severity
from radar.alerts.rules import (
    BasisBlowoutRule,
    FundingExtremeRule,
    LiquidationCascadeRule,
    OISurgeRule,
)


def _ctx(payload: dict[str, Any]) -> RuleContext:
    return RuleContext(asset="BTC", now=datetime.now(UTC), payload=payload)


@pytest.mark.asyncio
async def test_funding_extreme_long_bias() -> None:
    rule = FundingExtremeRule()
    signal = await rule.evaluate(_ctx({"funding_rate": 0.001}))
    assert signal is not None
    assert signal.severity == Severity.HIGH
    assert signal.payload["side"] == "long"


@pytest.mark.asyncio
async def test_funding_extreme_short_bias() -> None:
    rule = FundingExtremeRule()
    signal = await rule.evaluate(_ctx({"funding_rate": -0.0005}))
    assert signal is not None
    assert signal.payload["side"] == "short"


@pytest.mark.asyncio
async def test_funding_extreme_silent_when_in_corridor() -> None:
    rule = FundingExtremeRule()
    assert await rule.evaluate(_ctx({"funding_rate": 0.0001})) is None


@pytest.mark.asyncio
async def test_oi_surge_fires_when_oi_jumps_and_price_flat() -> None:
    rule = OISurgeRule()
    signal = await rule.evaluate(
        _ctx(
            {
                "oi_24h_ago_usd": 1_000_000,
                "oi_now_usd": 1_200_000,
                "price_24h_ago": 50_000,
                "price_now": 50_500,
            }
        )
    )
    assert signal is not None
    assert signal.payload["oi_change_pct"] > 15
    assert abs(signal.payload["price_change_pct"]) < 3


@pytest.mark.asyncio
async def test_oi_surge_silent_when_price_moved_too_much() -> None:
    rule = OISurgeRule()
    signal = await rule.evaluate(
        _ctx(
            {
                "oi_24h_ago_usd": 1_000_000,
                "oi_now_usd": 1_200_000,
                "price_24h_ago": 50_000,
                "price_now": 53_000,
            }
        )
    )
    assert signal is None


@pytest.mark.asyncio
async def test_oi_surge_silent_with_missing_payload() -> None:
    rule = OISurgeRule()
    assert await rule.evaluate(_ctx({})) is None


@pytest.mark.asyncio
async def test_basis_blowout_premium_zone() -> None:
    rule = BasisBlowoutRule()
    # 0.0003 * 3 * 365 = 0.3285 > 0.25 → fires premium
    signal = await rule.evaluate(_ctx({"funding_rate": 0.0003}))
    assert signal is not None
    assert signal.payload["basis_annualized"] > 0.25


@pytest.mark.asyncio
async def test_basis_blowout_discount_zone() -> None:
    rule = BasisBlowoutRule()
    # -0.0001 * 3 * 365 = -0.1095 < -0.10 → fires discount
    signal = await rule.evaluate(_ctx({"funding_rate": -0.0001}))
    assert signal is not None
    assert signal.payload["basis_annualized"] < -0.10


@pytest.mark.asyncio
async def test_basis_blowout_silent_inside_corridor() -> None:
    rule = BasisBlowoutRule()
    assert await rule.evaluate(_ctx({"funding_rate": 0.00005})) is None


@pytest.mark.asyncio
async def test_liq_cascade_silent_without_payload() -> None:
    rule = LiquidationCascadeRule()
    assert await rule.evaluate(_ctx({})) is None


@pytest.mark.asyncio
async def test_liq_cascade_fires_for_major_long_cascade() -> None:
    rule = LiquidationCascadeRule()
    signal = await rule.evaluate(
        _ctx(
            {
                "liq_long_usd_1h": 60_000_000,
                "liq_short_usd_1h": 0,
                "is_major": True,
            }
        )
    )
    assert signal is not None
    assert signal.severity == Severity.CRITICAL
    assert signal.payload["side"] == "long"


@pytest.mark.asyncio
async def test_liq_cascade_silent_below_minor_threshold() -> None:
    rule = LiquidationCascadeRule()
    signal = await rule.evaluate(
        _ctx(
            {
                "liq_long_usd_1h": 5_000_000,
                "liq_short_usd_1h": 4_000_000,
                "is_major": False,
            }
        )
    )
    assert signal is None
