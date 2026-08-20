from datetime import UTC, date, datetime
from pathlib import Path

import aiosqlite
import pytest

from asx_investigator.storage.repository import (
    CaseVersionImmutableError,
    SQLiteCaseRepository,
)


@pytest.fixture
async def repository(tmp_path: Path) -> SQLiteCaseRepository:
    value = SQLiteCaseRepository(tmp_path / "cases.db")
    await value.initialize()
    return value


async def test_case_events_are_append_only_and_replayable(
    repository: SQLiteCaseRepository,
) -> None:
    case = await repository.create_case(
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        mode="RECORDED",
        request_payload={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
    )

    first = await repository.append_event(case.version_id, "status", "resolve_session", "RUNNING")
    second = await repository.append_event(
        case.version_id, "stage", "market_forensics", "COMPLETED"
    )
    replay = await repository.list_events(case.version_id, after_sequence=first.sequence)

    assert first.sequence == 1
    assert second.sequence == 2
    assert [event.sequence for event in replay] == [2]


async def test_completed_version_is_immutable_and_child_retains_parent(
    repository: SQLiteCaseRepository,
) -> None:
    case = await repository.create_case(
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        mode="RECORDED",
        request_payload={"ticker": "BHP"},
    )
    await repository.complete_version(
        case.version_id,
        report_payload={"case_id": case.case_id, "status": "COMPLETED"},
        outcome="EXPLAINED",
    )

    with pytest.raises(CaseVersionImmutableError):
        await repository.update_status(case.version_id, "RUNNING", active_stage="retry")

    child = await repository.create_version(
        case.case_id,
        parent_version_id=case.version_id,
        request_payload={"ticker": "BHP", "primary_only": True},
    )

    assert child.version_number == 2
    assert child.parent_version_id == case.version_id


async def test_running_and_recoverable_versions_are_returned_after_restart(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "restart.db"
    first_process = SQLiteCaseRepository(database_path)
    await first_process.initialize()
    running = await first_process.create_case(
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        mode="LIVE",
        request_payload={"ticker": "BHP"},
    )
    await first_process.update_status(
        running.version_id, "FAILED_RECOVERABLE", active_stage="acquire_market"
    )

    second_process = SQLiteCaseRepository(database_path)
    await second_process.initialize()
    recoverable = await second_process.list_recoverable_versions()

    assert [item.version_id for item in recoverable] == [running.version_id]
    assert recoverable[0].active_stage == "acquire_market"


async def test_repository_enables_wal_mode(repository: SQLiteCaseRepository) -> None:
    assert await repository.journal_mode() == "wal"


async def test_repository_creates_provider_and_evidence_indexes(
    repository: SQLiteCaseRepository,
) -> None:
    async with aiosqlite.connect(repository.database_path) as connection:
        cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        tables = {row[0] for row in await cursor.fetchall()}

    assert {"provider_calls", "evidence_records"}.issubset(tables)


async def test_provider_calls_are_append_only_audit_records(
    repository: SQLiteCaseRepository,
) -> None:
    case = await repository.create_case(
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        mode="RECORDED",
        request_payload={"ticker": "BHP"},
    )

    await repository.record_provider_call(
        case.version_id,
        provider="EODHD",
        operation="daily_bars",
        status="SUCCESS",
        coverage="COMPLETE",
        retrieved_at=datetime.now(UTC),
        provenance={"symbol": "BHP.AU"},
        source_version="eod-v1",
    )
    calls = await repository.list_provider_calls(case.version_id)

    assert calls[0]["provider"] == "EODHD"
    assert calls[0]["provenance"] == {"symbol": "BHP.AU"}
