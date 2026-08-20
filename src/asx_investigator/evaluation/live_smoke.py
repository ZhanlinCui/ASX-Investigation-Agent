"""Bounded, auditable EODHD credentialed smoke gate."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from asx_investigator.domain.models import InstrumentIdentity
from asx_investigator.market.forensics import DailyBar
from asx_investigator.market.sessions import resolve_session
from asx_investigator.providers.errors import DataProviderUnavailable
from asx_investigator.providers.live import LiveToolGateway
from asx_investigator.providers.market import CorporateAction, MarketDataResult
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus
from asx_investigator.settings import Settings
from asx_investigator.storage.artifacts import ArtifactStore

SYDNEY = ZoneInfo("Australia/Sydney")


class SmokeStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


class ProviderSmokeResult(BaseModel):
    provider: str
    status: ProviderStatus
    coverage: str
    data_count: int = Field(ge=0)
    error_code: str | None = None
    source_version: str | None = None
    retrieved_at: datetime
    as_of: datetime | None = None
    artifact_id: str | None = None
    artifact_sha256: str | None = None


class MarketSmokeResult(ProviderSmokeResult):
    selected_provider: str | None = None
    target_session_present: bool = False


class EODHDSmokeGateway(Protocol):
    """The deliberately narrow provider surface permitted to the smoke gate."""

    async def close(self) -> None: ...

    async def resolve_eodhd_instrument(
        self, ticker: str
    ) -> tuple[InstrumentIdentity, ProviderOutcome[InstrumentIdentity]]: ...

    async def get_eodhd_market_data(
        self, ticker: str, trade_date: date
    ) -> MarketDataResult: ...

    async def get_corporate_actions(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[CorporateAction]]: ...


class LiveSmokeReport(BaseModel):
    schema_version: str = "live-smoke-v1"
    status: SmokeStatus
    evaluated_at: datetime
    ticker: str
    trade_date: date
    reason: str | None = None
    instrument: InstrumentIdentity | None = None
    instrument_resolution: ProviderSmokeResult | None = None
    market: MarketSmokeResult | None = None
    corporate_actions: ProviderSmokeResult | None = None


def _sydney(value: datetime | None) -> datetime | None:
    return value.astimezone(SYDNEY) if value is not None else None


def _provider_result[T](outcome: ProviderOutcome[T]) -> ProviderSmokeResult:
    data_count = (
        len(outcome.data) if isinstance(outcome.data, list) else int(outcome.data is not None)
    )
    return ProviderSmokeResult(
        provider=outcome.provider,
        status=outcome.status,
        coverage=outcome.coverage,
        data_count=data_count,
        error_code=outcome.error_code,
        source_version=outcome.source_version,
        retrieved_at=outcome.retrieved_at.astimezone(SYDNEY),
        as_of=_sydney(outcome.as_of),
        artifact_id=outcome.artifact.artifact_id if outcome.artifact else None,
        artifact_sha256=outcome.artifact.sha256 if outcome.artifact else None,
    )


def _market_result(
    outcome: ProviderOutcome[list[DailyBar]],
    *,
    selected_provider: str | None,
    trade_date: date,
) -> MarketSmokeResult:
    return MarketSmokeResult(
        **_provider_result(outcome).model_dump(),
        selected_provider=selected_provider,
        target_session_present=any(bar.trade_date == trade_date for bar in outcome.data or []),
    )


def _report(
    *,
    status: SmokeStatus,
    ticker: str,
    trade_date: date,
    reason: str | None = None,
    instrument: InstrumentIdentity | None = None,
    instrument_resolution: ProviderSmokeResult | None = None,
    market: MarketSmokeResult | None = None,
    corporate_actions: ProviderSmokeResult | None = None,
) -> LiveSmokeReport:
    return LiveSmokeReport(
        status=status,
        evaluated_at=datetime.now(SYDNEY),
        ticker=ticker.upper(),
        trade_date=trade_date,
        reason=reason,
        instrument=instrument,
        instrument_resolution=instrument_resolution,
        market=market,
        corporate_actions=corporate_actions,
    )


def _provider_outcome(
    outcomes: list[ProviderOutcome[object]], *, provider: str
) -> ProviderOutcome[object] | None:
    for outcome in outcomes:
        if outcome.provider == provider:
            return ProviderOutcome[object].model_validate(outcome)
    return None


async def run_eodhd_live_smoke(
    settings: Settings,
    *,
    ticker: str,
    trade_date: date,
    artifact_dir: Path,
    gateway: EODHDSmokeGateway | None = None,
) -> LiveSmokeReport:
    """Run one EODHD-only ASX smoke without generating an investigation report."""

    normalized_ticker = ticker.strip().upper()
    if not settings.eodhd_api_key:
        return _report(
            status=SmokeStatus.NOT_RUN,
            ticker=normalized_ticker,
            trade_date=trade_date,
            reason="EODHD_API_KEY is not configured.",
        )
    session = resolve_session(trade_date)
    if not session.is_trading_day:
        return _report(
            status=SmokeStatus.FAIL,
            ticker=normalized_ticker,
            trade_date=trade_date,
            reason="NOT_A_TRADING_DAY",
        )
    assert session.market_close is not None
    if datetime.now(SYDNEY) < session.market_close:
        return _report(
            status=SmokeStatus.FAIL,
            ticker=normalized_ticker,
            trade_date=trade_date,
            reason="SESSION_NOT_COMPLETED",
        )

    owns_gateway = gateway is None
    live_gateway = gateway or LiveToolGateway(settings, artifacts=ArtifactStore(artifact_dir))
    try:
        try:
            instrument, resolution = await live_gateway.resolve_eodhd_instrument(normalized_ticker)
        except LookupError:
            return _report(
                status=SmokeStatus.FAIL,
                ticker=normalized_ticker,
                trade_date=trade_date,
                reason="INSTRUMENT_NOT_FOUND",
            )
        except DataProviderUnavailable as error:
            outcome = _provider_outcome(error.outcomes, provider="EODHD_SEARCH")
            return _report(
                status=SmokeStatus.FAIL,
                ticker=normalized_ticker,
                trade_date=trade_date,
                reason="INSTRUMENT_UNAVAILABLE",
                instrument_resolution=(
                    _provider_result(outcome) if outcome is not None else None
                ),
            )
        resolution_result = _provider_result(resolution)
        if resolution.status != ProviderStatus.SUCCESS or resolution.artifact is None:
            return _report(
                status=SmokeStatus.FAIL,
                ticker=normalized_ticker,
                trade_date=trade_date,
                reason="EODHD_SEARCH_INCOMPLETE",
                instrument=instrument,
                instrument_resolution=resolution_result,
            )

        try:
            market_data = await live_gateway.get_eodhd_market_data(normalized_ticker, trade_date)
        except DataProviderUnavailable as error:
            outcome = _provider_outcome(error.outcomes, provider="EODHD")
            return _report(
                status=SmokeStatus.FAIL,
                ticker=normalized_ticker,
                trade_date=trade_date,
                reason="MARKET_DATA_UNAVAILABLE",
                instrument=instrument,
                market=(
                    _market_result(
                        ProviderOutcome[list[DailyBar]].model_validate(outcome),
                        selected_provider=None,
                        trade_date=trade_date,
                    )
                    if outcome is not None
                    else None
                ),
                instrument_resolution=resolution_result,
            )

        primary = next(
            (outcome for outcome in market_data.outcomes if outcome.provider == "EODHD"),
            None,
        )
        if primary is None:
            return _report(
                status=SmokeStatus.FAIL,
                ticker=normalized_ticker,
                trade_date=trade_date,
                reason="EODHD_PRIMARY_OUTCOME_MISSING",
                instrument=instrument,
                instrument_resolution=resolution_result,
            )
        market = _market_result(
            primary,
            selected_provider=market_data.selected_provider,
            trade_date=trade_date,
        )
        if (
            primary.status != ProviderStatus.SUCCESS
            or market_data.selected_provider != "EODHD"
            or not market.target_session_present
            or primary.artifact is None
        ):
            return _report(
                status=SmokeStatus.FAIL,
                ticker=normalized_ticker,
                trade_date=trade_date,
                reason="EODHD_PRIMARY_INCOMPLETE",
                instrument=instrument,
                market=market,
                instrument_resolution=resolution_result,
            )

        try:
            actions = await live_gateway.get_corporate_actions(normalized_ticker, trade_date)
        except DataProviderUnavailable:
            return _report(
                status=SmokeStatus.FAIL,
                ticker=normalized_ticker,
                trade_date=trade_date,
                reason="CORPORATE_ACTIONS_UNAVAILABLE",
                instrument=instrument,
                market=market,
                instrument_resolution=resolution_result,
            )
        corporate_actions = _provider_result(actions)
        if (
            actions.status not in {ProviderStatus.SUCCESS, ProviderStatus.EMPTY}
            or actions.artifact is None
        ):
            return _report(
                status=SmokeStatus.FAIL,
                ticker=normalized_ticker,
                trade_date=trade_date,
                reason="CORPORATE_ACTIONS_UNAVAILABLE",
                instrument=instrument,
                market=market,
                corporate_actions=corporate_actions,
                instrument_resolution=resolution_result,
            )
        return _report(
            status=SmokeStatus.PASS,
            ticker=normalized_ticker,
            trade_date=trade_date,
            instrument=instrument,
            market=market,
            corporate_actions=corporate_actions,
            instrument_resolution=resolution_result,
        )
    finally:
        if owns_gateway:
            await live_gateway.close()
