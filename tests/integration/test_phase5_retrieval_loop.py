from __future__ import annotations

from datetime import date

from asx_investigator.investigation.checkpoints import CheckpointEnvelope
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.errors import DataProviderUnavailable
from asx_investigator.providers.recorded import RecordedToolGateway


class _PlannedRecordedTools:
    def __init__(self) -> None:
        self.delegate = RecordedToolGateway.default()
        self.planned_tasks: list[tuple[str, str]] = []

    async def resolve_instrument(self, ticker: str):
        return await self.delegate.resolve_instrument(ticker)

    async def get_market_data(self, ticker: str, trade_date: date):
        return await self.delegate.get_market_data(ticker, trade_date)

    async def get_benchmark_return(self, trade_date: date):
        return await self.delegate.get_benchmark_return(trade_date)

    async def get_corporate_actions(self, ticker: str, trade_date: date):
        return await self.delegate.get_corporate_actions(ticker, trade_date)

    async def execute_retrieval_task(self, ticker: str, trade_date: date, task):
        self.planned_tasks.append((task.task_id, str(task.lane)))
        if str(task.lane) == "ISSUER_DISCLOSURE":
            return await self.delegate.get_evidence(ticker, trade_date)
        return []

    async def get_evidence(self, ticker: str, trade_date: date):
        raise AssertionError("kernel must use the sealed retrieval plan")

    async def targeted_retrieve(self, ticker: str, trade_date: date, query: str, purpose: str):
        return []

    async def disclosure_coverage_complete(self, ticker: str, trade_date: date):
        return await self.delegate.disclosure_coverage_complete(ticker, trade_date)


async def test_kernel_executes_each_sealed_initial_lane_and_persists_safe_results() -> None:
    tools = _PlannedRecordedTools()
    service = InvestigationService(tools)
    checkpoints: list[CheckpointEnvelope] = []

    async def observe(stage: str, status: str, payload: dict[str, object]) -> None:
        if stage == "discover_and_freeze_documents" and status == "COMPLETED":
            checkpoints.append(CheckpointEnvelope.model_validate(payload["checkpoint"]))

    report = await service.investigate(
        "BHP",
        "2026-08-20",
        mode="RECORDED",
        version_id="phase5-plan-execution",
        request_artifact_hash="a" * 64,
        input_artifact_hashes=["a" * 64],
        on_stage=observe,
    )

    assert [lane for _, lane in tools.planned_tasks] == [
        "ISSUER_DISCLOSURE",
        "CAPITAL_AND_CORPORATE_ACTION",
        "INDEX_REBALANCE",
        "SECTOR_AND_PEER",
        "NO_CATALYST_CONTROL",
    ]
    assert report.outcome == "EXPLAINED"
    state = checkpoints[0].typed_state_json
    assert [item["task_id"] for item in state["retrieval_results"]] == [
        task_id for task_id, _ in tools.planned_tasks
    ]
    assert all("query" not in item for item in state["retrieval_results"])


async def test_recorded_gateway_implements_the_same_planned_retrieval_contract() -> None:
    service = InvestigationService(RecordedToolGateway.default())
    checkpoints: list[CheckpointEnvelope] = []

    async def observe(stage: str, status: str, payload: dict[str, object]) -> None:
        if stage == "discover_and_freeze_documents" and status == "COMPLETED":
            checkpoints.append(CheckpointEnvelope.model_validate(payload["checkpoint"]))

    await service.investigate(
        "BHP",
        "2026-08-20",
        mode="RECORDED",
        version_id="phase5-recorded-contract",
        request_artifact_hash="b" * 64,
        input_artifact_hashes=["b" * 64],
        on_stage=observe,
    )

    results = checkpoints[0].typed_state_json["retrieval_results"]
    assert results
    assert all(item["status"] == "COMPLETE" for item in results)


async def test_failed_required_retrieval_lane_abstains_and_exposes_coverage_gap() -> None:
    class _FailedLaneTools(_PlannedRecordedTools):
        async def execute_retrieval_task(self, ticker: str, trade_date: date, task):
            if str(task.lane) == "INDEX_REBALANCE":
                raise DataProviderUnavailable("index source unavailable")
            return await super().execute_retrieval_task(ticker, trade_date, task)

    report = await InvestigationService(_FailedLaneTools()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.outcome == "INSUFFICIENT_EVIDENCE"
    assert report.coverage_status == "INCOMPLETE_RETRIEVAL_COVERAGE"
    assert "RETRIEVAL_R3_FAILED" in {gap.gap_id for gap in report.coverage_gaps}
    assert all(claim.claim_type != "CAUSE" for claim in report.claims)
