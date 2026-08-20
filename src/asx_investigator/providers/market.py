from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from asx_investigator.domain.models import CoverageGap, SourceConflict, TradingSession
from asx_investigator.market.forensics import DailyBar
from asx_investigator.market.sessions import classify_event
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus


class MarketDataProvider(Protocol):
    name: str

    async def get_daily_bars(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[DailyBar]]: ...


class CorporateAction(BaseModel):
    """An effective action plus the source timing needed to use it causally.

    `announced_at` is the provider-supplied timestamp at which the official action
    was announced or otherwise available. It is deliberately optional: an
    effective date is useful context, but it is not proof that the market could
    have known about the action before the investigated ASX session.
    """

    action_type: str
    effective_date: date
    announced_at: datetime | None = None
    adjustment_factor: float | None = None
    cash_amount_aud: float | None = None
    source_id: str

    @model_validator(mode="after")
    def validate_announcement_timestamp(self) -> CorporateAction:
        if self.announced_at is not None and self.announced_at.tzinfo is None:
            raise ValueError("announced_at must be timezone-aware")
        return self


def action_is_same_day_causal(
    action: CorporateAction,
    outcome: ProviderOutcome[list[CorporateAction]],
    session: TradingSession,
) -> bool:
    """Return whether a corporate action has auditable same-session timing.

    A result retrieved later is safe only when its source attests an immutable
    point-in-time snapshot (`as_of`) that includes a real action announcement.
    Neither an effective date nor the process retrieval time is used as a
    substitute publication timestamp.
    """

    if (
        action.announced_at is None
        or outcome.as_of is None
        or not session.is_trading_day
        or session.market_close is None
        or action.effective_date != session.trade_date
    ):
        return False
    if action.announced_at > outcome.as_of or outcome.as_of > session.market_close:
        return False
    return classify_event(action.announced_at, session).eligible_same_day_cause


class MarketContextSnapshot(BaseModel):
    """Point-in-time context; absent series remain absent rather than inferred."""

    as_of: date
    benchmark_return_pct: float | None = None
    fx_returns_pct: dict[str, float] = Field(default_factory=dict)
    commodity_returns_pct: dict[str, float] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)


class CorporateActionProvider(Protocol):
    name: str

    async def get_corporate_actions(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[CorporateAction]]: ...


class MarketContextProvider(Protocol):
    name: str

    async def get_market_context(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[MarketContextSnapshot]: ...


@dataclass(frozen=True)
class MarketDataResult:
    bars: list[DailyBar]
    selected_provider: str
    outcomes: list[ProviderOutcome[list[DailyBar]]]
    conflicts: list[SourceConflict] = field(default_factory=list)
    coverage_gap: CoverageGap | None = None


class MarketDataUnavailable(RuntimeError):
    def __init__(self, outcomes: list[ProviderOutcome[list[DailyBar]]]) -> None:
        super().__init__("No configured market-data provider returned usable history")
        self.outcomes = outcomes


def within_live_window(trade_date: date, *, today: date) -> bool:
    age_days = (today - trade_date).days
    return 0 <= age_days <= 365


class MarketDataReconciler:
    """Select one source by policy and preserve material disagreements."""

    def __init__(
        self,
        primary: MarketDataProvider,
        fallback: MarketDataProvider | None = None,
    ) -> None:
        self.primary = primary
        self.fallback = fallback

    async def acquire(self, ticker: str, trade_date: date) -> MarketDataResult:
        primary = await self.primary.get_daily_bars(ticker, trade_date)
        outcomes = [primary]
        secondary = (
            await self.fallback.get_daily_bars(ticker, trade_date) if self.fallback else None
        )
        if secondary is not None:
            outcomes.append(secondary)

        if primary.status == ProviderStatus.SUCCESS and primary.data:
            conflicts = (
                self._compare(primary, secondary)
                if secondary and secondary.succeeded and secondary.data
                else []
            )
            return MarketDataResult(
                bars=primary.data,
                selected_provider=primary.provider,
                outcomes=outcomes,
                conflicts=conflicts,
            )

        if secondary and secondary.status in {
            ProviderStatus.SUCCESS,
            ProviderStatus.PARTIAL,
        } and secondary.data:
            return MarketDataResult(
                bars=secondary.data,
                selected_provider=secondary.provider,
                outcomes=outcomes,
                coverage_gap=CoverageGap(
                    gap_id="MARKET_PRIMARY_UNAVAILABLE",
                    capability="market_data_primary",
                    provider=primary.provider,
                    reason=primary.error_code or str(primary.status),
                    impact="Fallback market data selected; source coverage is partial.",
                    retryable=primary.status == ProviderStatus.RETRYABLE_FAILURE,
                ),
            )
        raise MarketDataUnavailable(outcomes)

    @staticmethod
    def _compare(
        primary: ProviderOutcome[list[DailyBar]],
        secondary: ProviderOutcome[list[DailyBar]],
    ) -> list[SourceConflict]:
        assert primary.data and secondary.data
        left = primary.data[-1]
        right = secondary.data[-1]
        conflicts: list[SourceConflict] = []
        for field_name in ("open", "high", "low", "close"):
            primary_value = float(getattr(left, field_name))
            secondary_value = float(getattr(right, field_name))
            relative_difference = abs(primary_value - secondary_value) / abs(primary_value)
            if relative_difference > 0.005:
                conflicts.append(
                    SourceConflict(
                        conflict_id=f"MARKET_{field_name.upper()}",
                        field=field_name,
                        primary_source=primary.provider,
                        primary_value=f"{primary_value:.6f}",
                        secondary_source=secondary.provider,
                        secondary_value=f"{secondary_value:.6f}",
                        resolution=(
                            f"{primary.provider} selected by field policy; values not averaged."
                        ),
                    )
                )
        volume_difference = abs(left.volume - right.volume) / max(abs(left.volume), 1)
        if volume_difference > 0.05:
            conflicts.append(
                SourceConflict(
                    conflict_id="MARKET_VOLUME",
                    field="volume",
                    primary_source=primary.provider,
                    primary_value=str(left.volume),
                    secondary_source=secondary.provider,
                    secondary_value=str(right.volume),
                    resolution=(
                        f"{primary.provider} selected by field policy; values not averaged."
                    ),
                )
            )
        return conflicts
