from datetime import date

import pytest

from asx_investigator.investigation.checkpoints import CheckpointEnvelope
from asx_investigator.investigation.kernel import InvestigationKernel
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway


async def test_kernel_records_hash_bound_append_only_ledger_entries() -> None:
    service = InvestigationService(RecordedToolGateway.default())

    report = await service.investigate("BHP", "2026-08-20", mode="RECORDED")

    assert isinstance(service.kernel, InvestigationKernel)
    assert [entry.stage for entry in report.ledger][:3] == [
        "resolve_instrument",
        "resolve_asx_session",
        "acquire_market_data",
    ]
    assert all(entry.input_hashes for entry in report.ledger)
    assert report.ledger[-1].status == "COMPLETED"


class _FailOnceRecordedTools:
    def __init__(self) -> None:
        self.delegate = RecordedToolGateway.default()
        self.market_calls = 0
        self.fail_corporate_actions = True

    async def resolve_instrument(self, ticker: str):
        return await self.delegate.resolve_instrument(ticker)

    async def get_market_data(self, ticker: str, trade_date: date):
        self.market_calls += 1
        return await self.delegate.get_market_data(ticker, trade_date)

    async def get_benchmark_return(self, trade_date: date):
        return await self.delegate.get_benchmark_return(trade_date)

    async def get_corporate_actions(self, ticker: str, trade_date: date):
        if self.fail_corporate_actions:
            self.fail_corporate_actions = False
            raise RuntimeError("interrupted after market checkpoint")
        return await self.delegate.get_corporate_actions(ticker, trade_date)

    async def get_evidence(self, ticker: str, trade_date: date):
        return await self.delegate.get_evidence(ticker, trade_date)

    async def targeted_retrieve(
        self, ticker: str, trade_date: date, query: str, purpose: str
    ):
        return await self.delegate.targeted_retrieve(ticker, trade_date, query, purpose)

    async def disclosure_coverage_complete(self, ticker: str, trade_date: date):
        return await self.delegate.disclosure_coverage_complete(ticker, trade_date)


async def test_resume_keeps_prior_ledger_entries_without_repeating_market_provider() -> None:
    tools = _FailOnceRecordedTools()
    service = InvestigationService(tools)
    checkpoints: list[CheckpointEnvelope] = []

    async def observe(stage: str, status: str, payload: dict[str, object]) -> None:
        if status == "COMPLETED" and "checkpoint" in payload:
            checkpoints.append(CheckpointEnvelope.model_validate(payload["checkpoint"]))

    request_hash = "d" * 64
    with pytest.raises(RuntimeError, match="after market checkpoint"):
        await service.investigate(
            "BHP",
            "2026-08-20",
            mode="RECORDED",
            version_id="version-1",
            request_artifact_hash=request_hash,
            input_artifact_hashes=[request_hash],
            on_stage=observe,
        )

    report = await service.investigate(
        "BHP",
        "2026-08-20",
        mode="RECORDED",
        version_id="version-1",
        request_artifact_hash=request_hash,
        input_artifact_hashes=[request_hash],
        resume_checkpoint=checkpoints[-1],
    )

    assert tools.market_calls == 1
    assert [entry.status for entry in report.ledger].count("RESUMED") == 1
    assert report.ledger[3].stage == "acquire_market_data"
    assert report.ledger[3].status == "RESUMED"
