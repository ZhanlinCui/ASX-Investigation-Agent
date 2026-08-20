from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import httpx

from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers import market_adapters
from asx_investigator.providers.capture import canonical_json_bytes, capture_provider_payload
from asx_investigator.providers.live import LiveToolGateway
from asx_investigator.providers.market import MarketDataResult
from asx_investigator.providers.market_adapters import EODHDProvider
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.settings import Settings
from asx_investigator.storage.artifacts import ArtifactStore


def _daily_bar_payload() -> list[dict[str, object]]:
    return [
        {
            "date": "2026-08-20",
            "open": 10.5,
            "high": 11.2,
            "low": 10.4,
            "close": 11.0,
            "adjusted_close": 10.9,
            "volume": 500_000,
        }
    ]


class _PartialReadFailure(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'{"partial":'
        raise httpx.ReadTimeout("read timed out")


async def test_eodhd_success_has_canonical_response_artifact(tmp_path: Path) -> None:
    payload = _daily_bar_payload()
    artifacts = ArtifactStore(tmp_path / "artifacts")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    provider = EODHDProvider("test-token", client, artifacts)

    outcome = await provider.get_daily_bars("BHP", date(2026, 8, 20))

    assert outcome.artifact is not None
    assert artifacts.get(outcome.artifact.artifact_id) == canonical_json_bytes(payload)


async def test_eodhd_http_failure_captures_status_and_payload(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path / "artifacts")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(429, json={"error": "rate limited"})
        )
    )
    provider = EODHDProvider("test-token", client, artifacts)

    outcome = await provider.get_daily_bars("BHP", date(2026, 8, 20))

    assert outcome.artifact is not None
    assert json.loads(artifacts.get(outcome.artifact.artifact_id)) == {
        "payload": {"error": "rate limited"},
        "status_code": 429,
    }


async def test_connect_failure_does_not_fabricate_an_artifact(tmp_path: Path) -> None:
    async def fail_connect(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    artifacts = ArtifactStore(tmp_path / "artifacts")
    provider = EODHDProvider(
        "test-token",
        httpx.AsyncClient(transport=httpx.MockTransport(fail_connect)),
        artifacts,
    )

    outcome = await provider.get_daily_bars("BHP", date(2026, 8, 20))

    assert outcome.error_code == "NETWORK_ERROR"
    assert outcome.artifact is None


async def test_oversized_provider_response_has_bounded_failure_artifact(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(market_adapters, "MAX_PROVIDER_RESPONSE_BYTES", 4)
    artifacts = ArtifactStore(tmp_path / "artifacts")
    provider = EODHDProvider(
        "test-token",
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"12345")
            )
        ),
        artifacts,
    )

    outcome = await provider.get_daily_bars("BHP", date(2026, 8, 20))

    assert outcome.error_code == "RESPONSE_TOO_LARGE"
    assert outcome.artifact is not None
    assert json.loads(artifacts.get(outcome.artifact.artifact_id)) == {
        "error_code": "RESPONSE_TOO_LARGE",
        "status_code": 200,
    }


async def test_partial_provider_response_is_frozen_before_read_failure(
    tmp_path: Path,
) -> None:
    artifacts = ArtifactStore(tmp_path / "artifacts")
    provider = EODHDProvider(
        "test-token",
        httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=_PartialReadFailure())
            )
        ),
        artifacts,
    )

    outcome = await provider.get_daily_bars("BHP", date(2026, 8, 20))

    assert outcome.error_code == "NETWORK_ERROR"
    assert outcome.artifact is not None
    assert json.loads(artifacts.get(outcome.artifact.artifact_id)) == {
        "body": '{"partial":',
        "error_code": "NETWORK_ERROR",
        "status_code": 200,
    }


async def test_live_gateway_threads_shared_store_to_corporate_actions(
    tmp_path: Path,
) -> None:
    payload = {"data": [], "meta": {"total": 0}}
    artifacts = ArtifactStore(tmp_path / "artifacts")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    gateway = LiveToolGateway(
        Settings(eodhd_api_key="test-token"), client, artifacts=artifacts
    )

    outcome = await gateway.get_corporate_actions("BHP", date(2026, 8, 20))

    assert outcome.artifact is not None
    assert artifacts.get(outcome.artifact.artifact_id) == canonical_json_bytes(payload)


class _ArtifactGateway:
    def __init__(self, artifacts: ArtifactStore) -> None:
        self.delegate = RecordedToolGateway.default()
        self.reference = capture_provider_payload(
            artifacts, {"provider": "recorded-test"}, "application/json"
        )

    def __getattr__(self, name: str):
        return getattr(self.delegate, name)

    async def get_market_data(self, ticker: str, trade_date: date) -> MarketDataResult:
        result = await self.delegate.get_market_data(ticker, trade_date)
        return MarketDataResult(
            bars=result.bars,
            selected_provider=result.selected_provider,
            outcomes=[
                item.model_copy(update={"artifact": self.reference})
                for item in result.outcomes
            ],
            conflicts=result.conflicts,
            coverage_gap=result.coverage_gap,
        )

    async def get_corporate_actions(self, ticker: str, trade_date: date):
        result = await self.delegate.get_corporate_actions(ticker, trade_date)
        return result.model_copy(update={"artifact": self.reference})


async def test_provider_diagnostics_surface_outcome_artifact_id(tmp_path: Path) -> None:
    gateway = _ArtifactGateway(ArtifactStore(tmp_path / "artifacts"))

    report = await InvestigationService(gateway).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.provider_diagnostics
    assert {
        item.artifact_id for item in report.provider_diagnostics
    } == {gateway.reference.artifact_id}


async def test_recorded_gateway_outcomes_remain_valid_without_artifacts() -> None:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.provider_diagnostics
    assert all(item.artifact_id is None for item in report.provider_diagnostics)
