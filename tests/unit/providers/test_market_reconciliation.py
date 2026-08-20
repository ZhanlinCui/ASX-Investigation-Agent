from datetime import UTC, date, datetime

import pytest

from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.market import (
    MarketContextSnapshot,
    MarketDataReconciler,
    MarketDataUnavailable,
    within_live_window,
)
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus


def bar(close: float, volume: int = 100_000) -> DailyBar:
    return DailyBar(
        trade_date=date(2026, 8, 20),
        open=10,
        high=11,
        low=9.8,
        close=close,
        adjusted_close=close,
        volume=volume,
    )


class StaticMarketProvider:
    def __init__(self, name: str, outcome: ProviderOutcome[list[DailyBar]]) -> None:
        self.name = name
        self.outcome = outcome
        self.calls = 0

    async def get_daily_bars(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[DailyBar]]:
        self.calls += 1
        return self.outcome


def outcome(
    provider: str,
    status: ProviderStatus,
    data: list[DailyBar] | None = None,
) -> ProviderOutcome[list[DailyBar]]:
    return ProviderOutcome[list[DailyBar]](
        provider=provider,
        status=status,
        retrieved_at=datetime.now(UTC),
        coverage="COMPLETE" if status == ProviderStatus.SUCCESS else "NONE",
        data=data,
        error_code=None if status == ProviderStatus.SUCCESS else "UPSTREAM_UNAVAILABLE",
    )


async def test_primary_is_selected_and_material_disagreement_is_preserved() -> None:
    primary = StaticMarketProvider("EODHD", outcome("EODHD", ProviderStatus.SUCCESS, [bar(11)]))
    fallback = StaticMarketProvider(
        "Marketstack",
        outcome("Marketstack", ProviderStatus.SUCCESS, [bar(10.9, volume=110_000)]),
    )

    result = await MarketDataReconciler(primary, fallback).acquire(
        "BHP", date(2026, 8, 20)
    )

    assert result.selected_provider == "EODHD"
    assert result.bars[-1].close == 11
    assert {conflict.field for conflict in result.conflicts} == {"close", "volume"}
    assert all("not averaged" in conflict.resolution for conflict in result.conflicts)


async def test_fallback_is_used_only_when_primary_does_not_succeed() -> None:
    primary = StaticMarketProvider(
        "EODHD", outcome("EODHD", ProviderStatus.RETRYABLE_FAILURE)
    )
    fallback = StaticMarketProvider(
        "Marketstack", outcome("Marketstack", ProviderStatus.SUCCESS, [bar(10.9)])
    )

    result = await MarketDataReconciler(primary, fallback).acquire(
        "BHP", date(2026, 8, 20)
    )

    assert result.selected_provider == "Marketstack"
    assert result.coverage_gap is not None
    assert result.coverage_gap.provider == "EODHD"


async def test_partial_primary_uses_complete_fallback_without_mixing_bars() -> None:
    partial = outcome("EODHD", ProviderStatus.PARTIAL, [bar(10.8)])
    partial.coverage = "PARTIAL"
    partial.error_code = "MISSING_HISTORY"
    primary = StaticMarketProvider("EODHD", partial)
    fallback = StaticMarketProvider(
        "Marketstack", outcome("Marketstack", ProviderStatus.SUCCESS, [bar(10.9)])
    )

    result = await MarketDataReconciler(primary, fallback).acquire(
        "BHP", date(2026, 8, 20)
    )

    assert result.selected_provider == "Marketstack"
    assert result.bars[-1].close == 10.9
    assert result.coverage_gap is not None


def test_missing_market_context_remains_explicitly_unavailable() -> None:
    context = MarketContextSnapshot(as_of=date(2026, 8, 20))

    assert context.benchmark_return_pct is None
    assert context.fx_returns_pct == {}
    assert context.commodity_returns_pct == {}


async def test_all_provider_failures_remain_failures() -> None:
    primary = StaticMarketProvider(
        "EODHD", outcome("EODHD", ProviderStatus.RETRYABLE_FAILURE)
    )
    fallback = StaticMarketProvider(
        "Marketstack", outcome("Marketstack", ProviderStatus.PERMANENT_FAILURE)
    )

    with pytest.raises(MarketDataUnavailable) as caught:
        await MarketDataReconciler(primary, fallback).acquire("BHP", date(2026, 8, 20))

    assert [item.status for item in caught.value.outcomes] == [
        ProviderStatus.RETRYABLE_FAILURE,
        ProviderStatus.PERMANENT_FAILURE,
    ]


def test_live_window_is_trailing_twelve_months_and_rejects_future_dates() -> None:
    today = date(2026, 8, 20)

    assert within_live_window(date(2025, 8, 20), today=today) is True
    assert within_live_window(date(2025, 8, 18), today=today) is False
    assert within_live_window(date(2026, 8, 21), today=today) is False
