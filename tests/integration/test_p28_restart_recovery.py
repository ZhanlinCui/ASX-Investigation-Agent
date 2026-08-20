from __future__ import annotations

from pathlib import Path

import pytest
from test_p28_checkpoint_recovery import CountingTools, drain_manager, recorded_request

from asx_investigator.api.app import create_app
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.storage.repository import SQLiteCaseRepository


@pytest.mark.asyncio
async def test_startup_resumes_the_same_version_without_replaying_completed_providers(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cases.db"
    first_repository = SQLiteCaseRepository(database_path)
    tools = CountingTools(fail_once_at="get_corporate_actions")
    first_app = create_app(
        InvestigationService(tools),
        repository=first_repository,
    )

    async with first_app.router.lifespan_context(first_app):
        version = await first_app.state.case_manager.create(recorded_request())
        await drain_manager(first_app.state.case_manager)
        assert (await first_repository.get_version(version.version_id)).status == (
            "FAILED_RECOVERABLE"
        )
        before = dict(tools.calls)

    restarted_repository = SQLiteCaseRepository(database_path)
    restarted_app = create_app(
        InvestigationService(tools),
        repository=restarted_repository,
    )
    async with restarted_app.router.lifespan_context(restarted_app):
        await drain_manager(restarted_app.state.case_manager)

    completed = await restarted_repository.get_version(version.version_id)
    events = await restarted_repository.list_events(version.version_id)
    assert completed.status == "COMPLETED"
    assert tools.calls["resolve_instrument"] == before["resolve_instrument"]
    assert tools.calls["get_market_data"] == before["get_market_data"]
    assert tools.calls["get_benchmark_return"] == before["get_benchmark_return"]
    assert any(
        event.status == "RESUMED" and event.stage == "acquire_market_data"
        for event in events
    )


@pytest.mark.asyncio
async def test_startup_without_a_checkpoint_creates_an_audited_child_version(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cases.db"
    repository = SQLiteCaseRepository(database_path)
    await repository.initialize()
    parent = await repository.create_case(
        ticker="BHP",
        trade_date=recorded_request().trade_date,
        mode="RECORDED",
        request_payload=recorded_request().model_dump(mode="json"),
    )
    await repository.update_status(
        parent.version_id,
        "FAILED_RECOVERABLE",
        active_stage="resolve_instrument",
    )

    restarted_repository = SQLiteCaseRepository(database_path)
    restarted_app = create_app(
        InvestigationService(CountingTools()),
        repository=restarted_repository,
    )
    async with restarted_app.router.lifespan_context(restarted_app):
        await drain_manager(restarted_app.state.case_manager)

    child = await restarted_repository.get_case(parent.case_id)
    events = await restarted_repository.list_events(child.version_id)
    assert child.parent_version_id == parent.version_id
    assert child.version_id != parent.version_id
    assert child.status == "COMPLETED"
    assert any(event.status == "CHECKPOINT_INCOMPATIBLE" for event in events)


@pytest.mark.asyncio
async def test_startup_does_not_recover_a_superseded_nonterminal_version(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cases.db"
    repository = SQLiteCaseRepository(database_path)
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
    current = await repository.create_checkpoint_recovery_child(
        parent.version_id,
        request_payload=request.model_dump(mode="json"),
        reason="TEST_SUPERSEDED",
    )
    await repository.complete_version(
        current.version_id,
        report_payload={"status": "COMPLETED"},
        outcome="EXPLAINED",
    )

    restarted_repository = SQLiteCaseRepository(database_path)
    restarted_app = create_app(
        InvestigationService(CountingTools()),
        repository=restarted_repository,
    )
    async with restarted_app.router.lifespan_context(restarted_app):
        await drain_manager(restarted_app.state.case_manager)

    restored = await restarted_repository.get_case(parent.case_id)
    assert restored.version_id == current.version_id
    assert restored.status == "COMPLETED"


@pytest.mark.asyncio
async def test_startup_reclaims_running_current_version_with_valid_checkpoint(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cases.db"
    interrupted_repository = SQLiteCaseRepository(database_path)
    interrupted_tools = CountingTools(fail_once_at="get_corporate_actions")
    interrupted_app = create_app(
        InvestigationService(interrupted_tools), repository=interrupted_repository
    )

    async with interrupted_app.router.lifespan_context(interrupted_app):
        version = await interrupted_app.state.case_manager.create(recorded_request())
        await drain_manager(interrupted_app.state.case_manager)
        await interrupted_repository.update_status(
            version.version_id,
            "RUNNING",
            active_stage="acquire_market_data",
        )

    restarted_repository = SQLiteCaseRepository(database_path)
    restarted_tools = CountingTools()
    restarted_app = create_app(
        InvestigationService(restarted_tools), repository=restarted_repository
    )
    async with restarted_app.router.lifespan_context(restarted_app):
        await drain_manager(restarted_app.state.case_manager)

    restored = await restarted_repository.get_version(version.version_id)
    assert restored.status == "COMPLETED"
    assert restarted_tools.calls.get("resolve_instrument", 0) == 0
    assert restarted_tools.calls.get("get_market_data", 0) == 0
