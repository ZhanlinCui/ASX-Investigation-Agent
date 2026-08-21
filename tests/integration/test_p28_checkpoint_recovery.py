from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import date
from pathlib import Path

import aiosqlite
import pytest

from asx_investigator.api.app import InvestigationRequest, create_app
from asx_investigator.investigation.checkpoints import (
    CHECKPOINT_POLICY_VERSION,
    CHECKPOINT_SCHEMA_VERSION,
    InvestigationState,
)
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.market import MarketDataResult
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.storage.artifacts import ArtifactReference
from asx_investigator.storage.repository import SQLiteCaseRepository


class CountingTools:
    """Complete deterministic gateway that can fail once at a provider boundary."""

    def __init__(
        self,
        *,
        fail_once_at: str | None = None,
        with_artifacts: bool = False,
    ) -> None:
        self.delegate = RecordedToolGateway.default()
        self.fail_once_at = fail_once_at
        self.with_artifacts = with_artifacts
        self.calls: dict[str, int] = {}

    def _called(self, operation: str) -> None:
        self.calls[operation] = self.calls.get(operation, 0) + 1
        if self.fail_once_at == operation:
            self.fail_once_at = None
            raise RuntimeError(f"deterministic interruption at {operation}")

    async def resolve_instrument(self, ticker: str):
        self._called("resolve_instrument")
        return await self.delegate.resolve_instrument(ticker)

    async def get_daily_bars(self, ticker: str, trade_date: date):
        self._called("get_daily_bars")
        return await self.delegate.get_daily_bars(ticker, trade_date)

    async def get_market_data(self, ticker: str, trade_date: date):
        self._called("get_market_data")
        result = await self.delegate.get_market_data(ticker, trade_date)
        if not self.with_artifacts:
            return result
        return MarketDataResult(
            bars=result.bars,
            selected_provider=result.selected_provider,
            outcomes=[
                outcome.model_copy(
                    update={
                        "artifact": ArtifactReference(
                            artifact_id="a" * 64,
                            sha256="a" * 64,
                            mime_type="application/json",
                            size_bytes=1,
                        )
                    }
                )
                for outcome in result.outcomes
            ],
            conflicts=result.conflicts,
            coverage_gap=result.coverage_gap,
        )

    async def get_benchmark_return(self, trade_date: date):
        self._called("get_benchmark_return")
        return await self.delegate.get_benchmark_return(trade_date)

    async def get_corporate_actions(self, ticker: str, trade_date: date):
        self._called("get_corporate_actions")
        result = await self.delegate.get_corporate_actions(ticker, trade_date)
        if not self.with_artifacts:
            return result
        return result.model_copy(
            update={
                "artifact": ArtifactReference(
                    artifact_id="b" * 64,
                    sha256="b" * 64,
                    mime_type="application/json",
                    size_bytes=1,
                )
            }
        )

    async def get_evidence(self, ticker: str, trade_date: date):
        self._called("get_evidence")
        return await self.delegate.get_evidence(ticker, trade_date)

    async def targeted_retrieve(
        self,
        ticker: str,
        trade_date: date,
        query: str,
        purpose: str,
    ):
        self._called("targeted_retrieve")
        return await self.delegate.targeted_retrieve(ticker, trade_date, query, purpose)

    async def disclosure_coverage_complete(self, ticker: str, trade_date: date):
        self._called("disclosure_coverage_complete")
        return await self.delegate.disclosure_coverage_complete(ticker, trade_date)


class InterruptingReasoner:
    model_configuration = {"provider": "TEST", "structured_calls_max": "2"}

    async def generate(self, packet):
        raise RuntimeError("deterministic interruption at hypothesis generation")

    async def challenge(self, packet, hypotheses):
        raise AssertionError("challenge must not run after interrupted generation")


def recorded_request() -> InvestigationRequest:
    return InvestigationRequest(
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        mode="RECORDED",
    )


async def drain_manager(manager) -> None:
    while manager.tasks:
        await asyncio.gather(*tuple(manager.tasks))


@pytest.mark.asyncio
async def test_resume_after_market_checkpoint_does_not_repeat_completed_providers(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        interrupted = await repository.get_version(version.version_id)
        assert interrupted.status == "FAILED_RECOVERABLE"
        before = dict(tools.calls)

        retried = await app.state.case_manager.retry(version.version_id)
        await drain_manager(app.state.case_manager)

    completed = await repository.get_version(version.version_id)
    events = await repository.list_events(version.version_id)
    assert retried.version_id == version.version_id
    assert completed.status == "COMPLETED"
    assert tools.calls["resolve_instrument"] == before["resolve_instrument"]
    assert tools.calls["get_market_data"] == before["get_market_data"]
    assert tools.calls["get_benchmark_return"] == before["get_benchmark_return"]
    assert tools.calls["get_corporate_actions"] == before["get_corporate_actions"] + 1
    assert any(
        event.status == "RESUMED" and event.stage == "acquire_market_data"
        for event in events
    )


@pytest.mark.asyncio
async def test_concurrent_retry_queues_only_one_recovery_worker(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        before = dict(tools.calls)
        attempts = await asyncio.gather(
            app.state.case_manager.retry(version.version_id),
            app.state.case_manager.retry(version.version_id),
            return_exceptions=True,
        )
        await drain_manager(app.state.case_manager)

    assert sum(not isinstance(item, Exception) for item in attempts) == 1
    assert sum(isinstance(item, ValueError) for item in attempts) == 1
    assert tools.calls["get_corporate_actions"] == before["get_corporate_actions"] + 1


@pytest.mark.asyncio
async def test_checkpoints_bind_nonempty_input_hashes_to_the_normalized_request(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)

    async with aiosqlite.connect(repository.database_path) as connection:
        row = await (
            await connection.execute(
                """SELECT input_artifact_hashes_json, typed_state_json
                FROM checkpoints WHERE version_id = ? AND stage = 'acquire_market_data'""",
                (version.version_id,),
            )
        ).fetchone()

    assert row is not None
    input_hashes = json.loads(str(row[0]))
    typed_state = json.loads(str(row[1]))
    events = await repository.list_events(version.version_id)
    checkpoint_events = [event for event in events if "checkpoint" in event.payload]
    assert len(input_hashes) == 1
    assert len(input_hashes[0]) == 64
    assert typed_state["request_artifact_hash"] == input_hashes[0]
    assert checkpoint_events
    assert all(
        "typed_state_json" not in event.payload["checkpoint"]
        for event in checkpoint_events
    )


@pytest.mark.asyncio
async def test_incompatible_checkpoint_creates_child_retry(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        async with aiosqlite.connect(repository.database_path) as connection:
            await connection.execute(
                "UPDATE checkpoints SET policy_version = 'phase2-v2' WHERE version_id = ?",
                (version.version_id,),
            )
            await connection.commit()

        child = await app.state.case_manager.retry(version.version_id)
        await drain_manager(app.state.case_manager)

    parent = await repository.get_version(version.version_id)
    events = await repository.list_events(child.version_id)
    assert child.parent_version_id == version.version_id
    assert child.version_id != version.version_id
    assert parent.status == "FAILED"
    assert (await repository.get_version(child.version_id)).status == "COMPLETED"
    assert any(event.status == "CHECKPOINT_INCOMPATIBLE" for event in events)


@pytest.mark.asyncio
async def test_phase2_checkpoint_is_branched_before_any_resume(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        latest = await repository.latest_checkpoint(version.version_id)
        assert latest is not None
        legacy_state = dict(latest.typed_state_json)
        legacy_state.pop("ledger_schema_version")
        legacy_state.pop("ledger")
        legacy_state.pop("ledger_stage_output_hashes")
        async with aiosqlite.connect(repository.database_path) as connection:
            await connection.execute(
                """UPDATE checkpoints SET policy_version = 'phase2-v1',
                schema_version = 'checkpoint-v1', typed_state_json = ?
                WHERE version_id = ? AND stage = 'acquire_market_data'""",
                (json.dumps(legacy_state), version.version_id),
            )
            await connection.commit()

        child = await app.state.case_manager.retry(version.version_id)
        await drain_manager(app.state.case_manager)

    parent_events = await repository.list_events(version.version_id)
    assert child.parent_version_id == version.version_id
    assert child.version_id != version.version_id
    assert (await repository.get_version(version.version_id)).status == "FAILED"
    assert (await repository.get_version(child.version_id)).status == "COMPLETED"
    assert not any(event.status == "RESUMED" for event in parent_events)


@pytest.mark.asyncio
async def test_checkpoint_content_mismatch_creates_child_retry(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        async with aiosqlite.connect(repository.database_path) as connection:
            await connection.execute(
                """UPDATE checkpoints SET typed_state_json = ?
                WHERE version_id = ? AND stage = 'acquire_market_data'""",
                ("not-json", version.version_id),
            )
            await connection.commit()

        child = await app.state.case_manager.retry(version.version_id)
        await drain_manager(app.state.case_manager)

    assert child.parent_version_id == version.version_id
    assert child.version_id != version.version_id


@pytest.mark.asyncio
async def test_checkpoint_cannot_skip_state_beyond_its_completed_stage(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        before_market_calls = tools.calls["get_market_data"]
        async with aiosqlite.connect(repository.database_path) as connection:
            market_row = await (
                await connection.execute(
                    """SELECT typed_state_json FROM checkpoints
                    WHERE version_id = ? AND stage = 'acquire_market_data'""",
                    (version.version_id,),
                )
            ).fetchone()
            assert market_row is not None
            future_state = json.loads(str(market_row[0]))
            future_state["completed_stage"] = "resolve_asx_session"
            await connection.execute(
                """UPDATE checkpoints SET typed_state_json = ?
                WHERE version_id = ? AND stage = 'resolve_asx_session'""",
                (json.dumps(future_state), version.version_id),
            )
            await connection.execute(
                """DELETE FROM checkpoints
                WHERE version_id = ? AND stage = 'acquire_market_data'""",
                (version.version_id,),
            )
            await connection.commit()

        child = await app.state.case_manager.retry(version.version_id)
        await drain_manager(app.state.case_manager)

    assert child.parent_version_id == version.version_id
    assert tools.calls["get_market_data"] == before_market_calls + 1


@pytest.mark.asyncio
async def test_targeted_retrieval_lineage_freezes_prior_evidence_outputs(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="disclosure_coverage_complete")
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)

    async with aiosqlite.connect(repository.database_path) as connection:
        row = await (
            await connection.execute(
                """SELECT typed_state_json FROM checkpoints
                WHERE version_id = ? AND stage = 'discover_and_freeze_documents'""",
                (version.version_id,),
            )
        ).fetchone()
    assert row is not None
    state = InvestigationState.model_validate_json(str(row[0]))
    original_hash = hashlib.sha256(b"recorded-bhp-guidance-v1").hexdigest()
    new_hash = hashlib.sha256(b"targeted-evidence-v1").hexdigest()
    assert state.output_hashes() == [original_hash]

    assert state.evidence is not None
    state.evidence.append(
        state.evidence[0].model_copy(
            update={"evidence_id": "E2", "content_hash": "targeted-evidence-v1"}
        )
    )
    state.complete("targeted_retrieval")

    assert original_hash in state.input_hashes()
    assert new_hash not in state.input_hashes()
    assert state.output_hashes() == [new_hash]


@pytest.mark.asyncio
async def test_service_rejects_resume_when_current_input_artifacts_changed(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    service = InvestigationService(tools)
    app = create_app(service, repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)

    checkpoint = await repository.latest_checkpoint(version.version_id)
    assert checkpoint is not None
    state = InvestigationState.model_validate(checkpoint.typed_state_json)
    with pytest.raises(ValueError, match="input artifacts"):
        await service.investigate(
            "BHP",
            date(2026, 8, 20),
            mode="RECORDED",
            version_id=version.version_id,
            request_artifact_hash=state.request_artifact_hash,
            input_artifact_hashes=[state.request_artifact_hash, "a" * 64],
            resume_checkpoint=checkpoint,
        )


@pytest.mark.asyncio
async def test_incompatible_checkpoint_branch_persists_parent_child_and_events_together(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    await repository.initialize()
    request = recorded_request()
    parent = await repository.create_case(
        ticker=request.ticker,
        trade_date=request.trade_date,
        mode=request.mode,
        request_payload=request.model_dump(mode="json"),
    )
    await repository.update_status(
        parent.version_id,
        "FAILED_RECOVERABLE",
        active_stage="acquire_market_data",
    )

    child = await repository.create_checkpoint_recovery_child(
        parent.version_id,
        request_payload=request.model_dump(mode="json"),
        reason="POLICY_MISMATCH",
    )

    persisted_parent = await repository.get_version(parent.version_id)
    parent_events = await repository.list_events(parent.version_id)
    child_events = await repository.list_events(child.version_id)
    assert persisted_parent.status == "FAILED"
    assert child.parent_version_id == parent.version_id
    assert child.status == "QUEUED"
    assert (await repository.get_case(parent.case_id)).version_id == child.version_id
    assert parent_events[-1].status == "CHECKPOINT_INCOMPATIBLE"
    assert child_events[-1].status == "CHECKPOINT_INCOMPATIBLE"


@pytest.mark.asyncio
async def test_resume_after_documents_skips_all_prior_artifact_bearing_providers(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(
        fail_once_at="disclosure_coverage_complete",
        with_artifacts=True,
    )
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        before = dict(tools.calls)
        latest = await repository.latest_checkpoint(version.version_id)
        assert latest is not None
        assert latest.schema_version == CHECKPOINT_SCHEMA_VERSION
        assert latest.policy_version == CHECKPOINT_POLICY_VERSION
        checkpoint_state = InvestigationState.model_validate(latest.typed_state_json)
        market = await repository.latest_compatible_checkpoint(
            version.version_id,
            policy_version=CHECKPOINT_POLICY_VERSION,
            input_artifact_hashes=[checkpoint_state.request_artifact_hash],
        )
        assert market is not None
        assert market.output_artifact_hashes == ["a" * 64]
        assert latest is not None
        assert latest.stage == "discover_and_freeze_documents"
        assert {"a" * 64, "b" * 64} <= set(latest.input_artifact_hashes)

        retried = await app.state.case_manager.retry(version.version_id)
        await drain_manager(app.state.case_manager)

    assert retried.version_id == version.version_id
    for operation in (
        "resolve_instrument",
        "get_market_data",
        "get_benchmark_return",
        "get_corporate_actions",
        "get_evidence",
    ):
        assert tools.calls[operation] == before[operation]
    assert tools.calls["disclosure_coverage_complete"] == (
        before["disclosure_coverage_complete"] + 1
    )


@pytest.mark.asyncio
async def test_retry_rejects_superseded_version_even_with_valid_checkpoint(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        parent = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        assert (await repository.latest_checkpoint(parent.version_id)) is not None
        current = await repository.create_checkpoint_recovery_child(
            parent.version_id,
            request_payload=recorded_request().model_dump(mode="json"),
            reason="TEST_SUPERSEDED",
        )
        await repository.complete_version(
            current.version_id,
            report_payload={"status": "COMPLETED"},
            outcome="EXPLAINED",
        )

        with pytest.raises(ValueError, match="current"):
            await app.state.case_manager.retry(parent.version_id)

    persisted_parent = await repository.get_version(parent.version_id)
    persisted_current = await repository.get_case(parent.case_id)
    assert persisted_parent.status == "FAILED"
    assert persisted_current.version_id == current.version_id
    assert persisted_current.status == "COMPLETED"


@pytest.mark.asyncio
async def test_refinement_supersedes_a_nonterminal_current_version_safely(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    await repository.initialize()
    request = recorded_request()
    current = await repository.create_case(
        ticker=request.ticker,
        trade_date=request.trade_date,
        mode=request.mode,
        request_payload=request.model_dump(mode="json"),
    )

    child = await repository.create_version(
        current.case_id,
        parent_version_id=current.version_id,
        request_payload=request.model_dump(mode="json"),
    )

    assert child.parent_version_id == current.version_id
    assert (await repository.get_version(current.version_id)).error == "SUPERSEDED_BY_REFINEMENT"


@pytest.mark.asyncio
async def test_late_checkpoint_missing_earlier_prerequisites_creates_child(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    service = InvestigationService(
        CountingTools(),
        reasoner=InterruptingReasoner(),
    )
    app = create_app(service, repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        latest = await repository.latest_checkpoint(version.version_id)
        assert latest is not None
        assert latest.stage == "assemble_evidence_packet"
        malformed_state = dict(latest.typed_state_json)
        malformed_state["instrument"] = None
        malformed_state["session"] = None
        malformed_state["corporate_actions"] = None
        async with aiosqlite.connect(repository.database_path) as connection:
            await connection.execute(
                """UPDATE checkpoints SET typed_state_json = ?
                WHERE version_id = ? AND stage = 'assemble_evidence_packet'""",
                (json.dumps(malformed_state), version.version_id),
            )
            await connection.commit()

        child = await app.state.case_manager.retry(version.version_id)
        await drain_manager(app.state.case_manager)

    assert child.parent_version_id == version.version_id
    assert child.version_id != version.version_id
    assert (await repository.get_version(version.version_id)).status == "FAILED"


@pytest.mark.parametrize("mutation", ["alter_market", "omit_corporate"])
@pytest.mark.asyncio
async def test_late_checkpoint_cross_checks_every_prior_artifact_output(
    tmp_path: Path,
    mutation: str,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / f"{mutation}.db")
    tools = CountingTools(
        fail_once_at="disclosure_coverage_complete",
        with_artifacts=True,
    )
    app = create_app(InvestigationService(tools), repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)
        latest = await repository.latest_checkpoint(version.version_id)
        assert latest is not None
        state = dict(latest.typed_state_json)
        stage_outputs = dict(state["stage_output_artifact_hashes"])
        inputs = list(latest.input_artifact_hashes)
        if mutation == "alter_market":
            stage_outputs["acquire_market_data"] = ["c" * 64]
            inputs = ["c" * 64 if value == "a" * 64 else value for value in inputs]
        else:
            stage_outputs["test_mechanical_explanations"] = []
            inputs = [value for value in inputs if value != "b" * 64]
        state["stage_output_artifact_hashes"] = stage_outputs
        async with aiosqlite.connect(repository.database_path) as connection:
            await connection.execute(
                """UPDATE checkpoints SET typed_state_json = ?,
                input_artifact_hashes_json = ?
                WHERE version_id = ? AND stage = 'discover_and_freeze_documents'""",
                (json.dumps(state), json.dumps(inputs), version.version_id),
            )
            await connection.commit()

        child = await app.state.case_manager.retry(version.version_id)
        await drain_manager(app.state.case_manager)

    assert child.parent_version_id == version.version_id
    assert child.version_id != version.version_id


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("policy_version", "phase2-v2", "policy"),
        ("schema_version", f"{CHECKPOINT_SCHEMA_VERSION}-unsupported", "schema"),
    ],
)
@pytest.mark.asyncio
async def test_service_rejects_unsupported_checkpoint_contract_before_resume(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / f"{field}.db")
    tools = CountingTools(fail_once_at="get_corporate_actions")
    service = InvestigationService(tools)
    app = create_app(service, repository=repository)

    async with app.router.lifespan_context(app):
        version = await app.state.case_manager.create(recorded_request())
        await drain_manager(app.state.case_manager)

    checkpoint = await repository.latest_checkpoint(version.version_id)
    assert checkpoint is not None
    state = InvestigationState.model_validate(checkpoint.typed_state_json)
    incompatible = checkpoint.model_copy(update={field: value})
    before = dict(tools.calls)
    with pytest.raises(ValueError, match=message):
        await service.investigate(
            "BHP",
            date(2026, 8, 20),
            mode="RECORDED",
            version_id=version.version_id,
            request_artifact_hash=state.request_artifact_hash,
            input_artifact_hashes=state.initial_input_artifact_hashes,
            resume_checkpoint=incompatible,
        )
    assert tools.calls == before
