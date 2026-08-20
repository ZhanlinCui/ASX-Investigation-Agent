from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from asx_investigator.domain.models import InstrumentIdentity
from asx_investigator.evaluation.live_smoke import (
    ProviderSmokeResult,
    SmokeStatus,
    run_eodhd_live_smoke,
)
from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.errors import DataProviderUnavailable
from asx_investigator.providers.live import LiveToolGateway
from asx_investigator.providers.market import CorporateAction, MarketDataResult
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus
from asx_investigator.settings import Settings
from asx_investigator.storage.artifacts import ArtifactReference, ArtifactStore


def _artifact(value: str = "a") -> ArtifactReference:
    return ArtifactReference(
        artifact_id=value * 64,
        sha256=value * 64,
        mime_type="application/json",
        size_bytes=10,
    )


def _market_outcome(
    status: ProviderStatus = ProviderStatus.SUCCESS,
) -> ProviderOutcome[list[DailyBar]]:
    return ProviderOutcome(
        status=status,
        provider="EODHD",
        retrieved_at=datetime(2026, 8, 21, 6, tzinfo=UTC),
        coverage="COMPLETE",
        data=[
            DailyBar(
                trade_date=date(2026, 8, 20),
                open=50.0,
                high=51.0,
                low=49.5,
                close=50.5,
                adjusted_close=50.5,
                volume=1_000_000,
            )
        ],
        provenance={"symbol": "BHP.AU"},
        source_version="eod-v1",
        artifact=_artifact(),
    )


def _resolution_outcome(
    instrument: InstrumentIdentity | None = None,
) -> ProviderOutcome[InstrumentIdentity]:
    return ProviderOutcome(
        status=ProviderStatus.SUCCESS,
        provider="EODHD_SEARCH",
        retrieved_at=datetime(2026, 8, 21, 6, tzinfo=UTC),
        coverage="COMPLETE",
        data=instrument or InstrumentIdentity(asx_code="BHP", company_name="BHP Group Limited"),
        provenance={"symbol": "BHP.AU", "endpoint": "search"},
        source_version="search-v1",
        artifact=_artifact("c"),
    )


def _corporate_outcome(
    status: ProviderStatus = ProviderStatus.EMPTY,
) -> ProviderOutcome[list[CorporateAction]]:
    return ProviderOutcome(
        status=status,
        provider="EODHD_ASX_CORPORATE_ACTIONS",
        retrieved_at=datetime(2026, 8, 21, 6, tzinfo=UTC),
        coverage="COMPLETE",
        data=[],
        provenance={"symbol": "BHP.AU"},
        source_version="asx-corporate-actions-beta-v1",
        artifact=_artifact("b"),
    )


class FakeLiveGateway:
    def __init__(
        self,
        *,
        market: MarketDataResult | None = None,
        corporate: ProviderOutcome[list[CorporateAction]] | None = None,
        resolution: ProviderOutcome[InstrumentIdentity] | None = None,
        market_error: DataProviderUnavailable | None = None,
    ) -> None:
        self.market = market or MarketDataResult(
            bars=_market_outcome().data or [],
            selected_provider="EODHD",
            outcomes=[_market_outcome()],
        )
        self.corporate = corporate or _corporate_outcome()
        self.resolution = resolution or _resolution_outcome()
        self.market_error = market_error
        self.calls: list[str] = []

    async def resolve_eodhd_instrument(
        self, ticker: str
    ) -> tuple[InstrumentIdentity, ProviderOutcome[InstrumentIdentity]]:
        self.calls.append("resolve")
        instrument = InstrumentIdentity(asx_code=ticker, company_name="BHP Group Limited")
        return instrument, self.resolution

    async def get_eodhd_market_data(
        self, ticker: str, trade_date: date
    ) -> MarketDataResult:
        self.calls.append("market")
        if self.market_error is not None:
            raise self.market_error
        return self.market

    async def get_corporate_actions(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[CorporateAction]]:
        self.calls.append("corporate")
        return self.corporate


async def test_live_smoke_is_not_run_without_eodhd_credentials(tmp_path: Path) -> None:
    report = await run_eodhd_live_smoke(
        Settings(),
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        artifact_dir=tmp_path,
    )

    assert report.status == SmokeStatus.NOT_RUN
    assert report.reason == "EODHD_API_KEY is not configured."


async def test_live_smoke_rejects_a_non_trading_asx_date_without_provider_calls(
    tmp_path: Path,
) -> None:
    gateway = FakeLiveGateway()

    report = await run_eodhd_live_smoke(
        Settings(eodhd_api_key="test-token"),
        ticker="BHP",
        trade_date=date(2026, 8, 23),
        artifact_dir=tmp_path,
        gateway=gateway,
    )

    assert report.status == SmokeStatus.FAIL
    assert report.reason == "NOT_A_TRADING_DAY"
    assert gateway.calls == []


async def test_live_smoke_rejects_an_unfinished_asx_session_without_provider_calls(
    tmp_path: Path,
) -> None:
    gateway = FakeLiveGateway()

    report = await run_eodhd_live_smoke(
        Settings(eodhd_api_key="test-token"),
        ticker="BHP",
        trade_date=date(2099, 8, 20),
        artifact_dir=tmp_path,
        gateway=gateway,
    )

    assert report.status == SmokeStatus.FAIL
    assert report.reason == "SESSION_NOT_COMPLETED"
    assert gateway.calls == []


async def test_live_smoke_reports_auditable_primary_and_empty_corporate_outcomes(
    tmp_path: Path,
) -> None:
    gateway = FakeLiveGateway()

    report = await run_eodhd_live_smoke(
        Settings(eodhd_api_key="test-token"),
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        artifact_dir=tmp_path,
        gateway=gateway,
    )

    assert report.status == SmokeStatus.PASS
    assert report.instrument is not None
    assert report.instrument.asx_code == "BHP"
    assert report.instrument_resolution is not None
    assert report.instrument_resolution.provider == "EODHD_SEARCH"
    assert report.instrument_resolution.artifact_id == "c" * 64
    assert report.market.selected_provider == "EODHD"
    assert report.market.artifact_id == "a" * 64
    assert report.corporate_actions.status == ProviderStatus.EMPTY
    assert report.corporate_actions.artifact_id == "b" * 64
    assert "+00:00" not in report.model_dump_json()
    assert gateway.calls == ["resolve", "market", "corporate"]


async def test_live_smoke_keeps_configured_eodhd_failure_visible(tmp_path: Path) -> None:
    failed = ProviderOutcome[list[DailyBar]](
        status=ProviderStatus.PERMANENT_FAILURE,
        provider="EODHD",
        retrieved_at=datetime(2026, 8, 21, 6, tzinfo=UTC),
        coverage="NONE",
        error_code="HTTP_401",
        source_version="eod-v1",
        artifact=_artifact(),
    )
    gateway = FakeLiveGateway(
        market_error=DataProviderUnavailable("Market data unavailable: HTTP_401", outcomes=[failed])
    )

    report = await run_eodhd_live_smoke(
        Settings(eodhd_api_key="test-token"),
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        artifact_dir=tmp_path,
        gateway=gateway,
    )

    assert report.status == SmokeStatus.FAIL
    assert report.reason == "MARKET_DATA_UNAVAILABLE"
    assert report.market.status == ProviderStatus.PERMANENT_FAILURE
    assert report.market.error_code == "HTTP_401"
    assert gateway.calls == ["resolve", "market"]


async def test_live_smoke_requires_a_frozen_instrument_resolution_artifact(
    tmp_path: Path,
) -> None:
    no_artifact = ProviderOutcome[InstrumentIdentity](
        status=ProviderStatus.SUCCESS,
        provider="EODHD_SEARCH",
        retrieved_at=datetime(2026, 8, 21, 6, tzinfo=UTC),
        coverage="COMPLETE",
        data=InstrumentIdentity(asx_code="BHP", company_name="BHP Group Limited"),
        provenance={"symbol": "BHP.AU", "endpoint": "search"},
        source_version="search-v1",
    )
    gateway = FakeLiveGateway(resolution=no_artifact)

    report = await run_eodhd_live_smoke(
        Settings(eodhd_api_key="test-token"),
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        artifact_dir=tmp_path,
        gateway=gateway,
    )

    assert report.status == SmokeStatus.FAIL
    assert report.reason == "EODHD_SEARCH_INCOMPLETE"
    assert report.instrument_resolution is not None
    assert report.instrument_resolution.artifact_id is None
    assert gateway.calls == ["resolve"]


async def test_live_smoke_maps_instrument_network_failure_to_safe_fail(tmp_path: Path) -> None:
    async def fail_network(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private transport detail", request=request)

    gateway = LiveToolGateway(
        Settings(eodhd_api_key="test-token"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(fail_network)),
        artifacts=ArtifactStore(tmp_path),
    )
    try:
        report = await run_eodhd_live_smoke(
            Settings(eodhd_api_key="test-token"),
            ticker="BHP",
            trade_date=date(2026, 8, 20),
            artifact_dir=tmp_path,
            gateway=gateway,
        )
    finally:
        await gateway.close()

    assert report.status == SmokeStatus.FAIL
    assert report.reason == "INSTRUMENT_UNAVAILABLE"
    assert "private transport detail" not in report.model_dump_json()


@pytest.mark.parametrize(
    "payload",
    [
        ["bad-row"],
        [{"Code": None, "Exchange": "AU"}],
        [{"Code": "BHP", "Exchange": "AU", "Name": {"bad": "shape"}}],
    ],
)
async def test_live_smoke_maps_instrument_schema_failure_to_safe_fail(
    tmp_path: Path, payload: list[object]
) -> None:
    gateway = LiveToolGateway(
        Settings(eodhd_api_key="test-token"),
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        ),
        artifacts=ArtifactStore(tmp_path),
    )
    try:
        report = await run_eodhd_live_smoke(
            Settings(eodhd_api_key="test-token"),
            ticker="BHP",
            trade_date=date(2026, 8, 20),
            artifact_dir=tmp_path,
            gateway=gateway,
        )
    finally:
        await gateway.close()

    assert report.status == SmokeStatus.FAIL
    assert report.reason == "INSTRUMENT_UNAVAILABLE"
    assert report.instrument_resolution is not None
    assert report.instrument_resolution.error_code == "SCHEMA_INVALID"


async def test_live_smoke_fails_for_missing_corporate_action_entitlement(tmp_path: Path) -> None:
    corporate = ProviderOutcome[list[CorporateAction]](
        status=ProviderStatus.PERMANENT_FAILURE,
        provider="EODHD_ASX_CORPORATE_ACTIONS",
        retrieved_at=datetime(2026, 8, 21, 6, tzinfo=UTC),
        coverage="NONE",
        error_code="HTTP_403",
        source_version="asx-corporate-actions-beta-v1",
        artifact=_artifact("b"),
    )
    gateway = FakeLiveGateway(corporate=corporate)

    report = await run_eodhd_live_smoke(
        Settings(eodhd_api_key="test-token"),
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        artifact_dir=tmp_path,
        gateway=gateway,
    )

    assert report.status == SmokeStatus.FAIL
    assert report.reason == "CORPORATE_ACTIONS_UNAVAILABLE"
    assert report.corporate_actions.error_code == "HTTP_403"


async def test_eodhd_primary_only_acquisition_never_calls_marketstack(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []
    trade_date = date(2026, 8, 20)
    rows = [
        {
            "date": (trade_date - timedelta(days=offset)).isoformat(),
            "open": 50.0,
            "high": 51.0,
            "low": 49.5,
            "close": 50.5,
            "adjusted_close": 50.5,
            "volume": 1_000_000,
        }
        for offset in range(41)
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.host == "eodhd.com"
        return httpx.Response(200, json=rows)

    gateway = LiveToolGateway(
        Settings(eodhd_api_key="test-token", marketstack_api_key="also-configured"),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        artifacts=ArtifactStore(tmp_path),
    )
    try:
        result = await gateway.get_eodhd_market_data("BHP", trade_date)
    finally:
        await gateway.close()

    assert result.selected_provider == "EODHD"
    assert [request.url.path for request in requests] == ["/api/eod/BHP.AU"]


async def test_eodhd_resolution_returns_a_safe_artifact_reference(tmp_path: Path) -> None:
    payload = [{"Code": "BHP", "Exchange": "AU", "Name": "BHP Group Limited"}]
    artifacts = ArtifactStore(tmp_path)
    gateway = LiveToolGateway(
        Settings(eodhd_api_key="test-token"),
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        ),
        artifacts=artifacts,
    )
    try:
        instrument, outcome = await gateway.resolve_eodhd_instrument("BHP")
    finally:
        await gateway.close()

    public = ProviderSmokeResult.model_validate(
        {
            "provider": outcome.provider,
            "status": outcome.status,
            "coverage": outcome.coverage,
            "data_count": 1,
            "retrieved_at": outcome.retrieved_at,
            "artifact_id": outcome.artifact.artifact_id if outcome.artifact else None,
            "artifact_sha256": outcome.artifact.sha256 if outcome.artifact else None,
        }
    )
    assert instrument.asx_code == "BHP"
    assert outcome.artifact is not None
    assert json.loads(artifacts.get(outcome.artifact.artifact_id)) == payload
    assert public.artifact_id == outcome.artifact.artifact_id
    assert "BHP Group Limited" not in public.model_dump_json()
