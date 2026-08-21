import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from asx_investigator.investigation.checkpoints import (
    CHECKPOINT_POLICY_VERSION,
    CHECKPOINT_SCHEMA_VERSION,
    CheckpointEnvelope,
    InvestigationState,
)
from asx_investigator.providers.capture import (
    canonical_json_bytes,
    capture_provider_payload,
    freeze_json_payload,
)
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus
from asx_investigator.storage.artifacts import ArtifactReference, ArtifactStore
from asx_investigator.storage.repository import CaseVersionRecord, SQLiteCaseRepository


@pytest.fixture
async def repository(tmp_path: Path) -> SQLiteCaseRepository:
    value = SQLiteCaseRepository(tmp_path / "cases.db")
    await value.initialize()
    return value


@pytest.fixture
async def case_version(repository: SQLiteCaseRepository) -> CaseVersionRecord:
    return await repository.create_case(
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        mode="RECORDED",
        request_payload={"ticker": "BHP"},
    )


@pytest.mark.asyncio
async def test_provider_capture_persists_canonical_json_before_parse(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = capture_provider_payload(
        store, {"close": 12.34, "symbol": "BHP.AU"}, "application/json"
    )

    assert store.get(artifact.artifact_id) == b'{"close":12.34,"symbol":"BHP.AU"}'
    assert artifact.sha256 == artifact.artifact_id


def test_capture_types_are_immutable_and_alias_the_canonical_serializer() -> None:
    reference = ArtifactReference(
        artifact_id="a" * 64,
        sha256="a" * 64,
        mime_type="application/json",
        size_bytes=1,
    )
    outcome = ProviderOutcome[dict[str, object]](
        status=ProviderStatus.SUCCESS,
        provider="example",
        retrieved_at=datetime.now(UTC),
        coverage="COMPLETE",
        data={},
        artifact=reference,
    )

    assert freeze_json_payload is canonical_json_bytes
    assert outcome.artifact == reference
    with pytest.raises(Exception):
        reference.mime_type = "text/plain"

    checkpoint = CheckpointEnvelope(
        version_id="version-1",
        stage="acquire_market_data",
        input_artifact_hashes=[],
        output_artifact_hashes=[],
        typed_state_json={},
        policy_version="phase2-v1",
    )
    with pytest.raises(Exception):
        checkpoint.stage = "different"


def test_p3_assertion_checkpoints_use_a_new_contract_and_field_name() -> None:
    state = InvestigationState(
        version_id="version-1",
        request_artifact_hash="a" * 64,
        initial_input_artifact_hashes=["a" * 64],
    )
    checkpoint = CheckpointEnvelope(
        version_id="version-1",
        stage="resolve_instrument",
        input_artifact_hashes=[],
        output_artifact_hashes=[],
        typed_state_json={},
        policy_version=CHECKPOINT_POLICY_VERSION,
    )

    assert CHECKPOINT_SCHEMA_VERSION == "checkpoint-v3"
    assert CHECKPOINT_POLICY_VERSION == "phase5-p5.1-v1"
    assert checkpoint.schema_version == CHECKPOINT_SCHEMA_VERSION
    assert "targeted_assertion_ids" in state.model_dump()
    assert "targeted_evidence_ids" not in state.model_dump()
    assert "retrieval_plan" in state.model_dump()
    assert "retrieval_results" in state.model_dump()


@pytest.mark.asyncio
async def test_latest_checkpoint_requires_same_schema_policy_and_input_hashes(
    repository: SQLiteCaseRepository, case_version: CaseVersionRecord
) -> None:
    checkpoint = CheckpointEnvelope(
        version_id=case_version.version_id,
        stage="acquire_market_data",
        input_artifact_hashes=["a" * 64],
        output_artifact_hashes=["b" * 64],
        typed_state_json={"instrument": {"asx_code": "BHP"}},
        policy_version="phase2-v1",
    )
    await repository.save_checkpoint(checkpoint)

    assert await repository.latest_compatible_checkpoint(
        case_version.version_id,
        policy_version="phase2-v1",
        input_artifact_hashes=["a" * 64],
    ) == checkpoint
    assert await repository.latest_compatible_checkpoint(
        case_version.version_id,
        policy_version="phase2-v2",
        input_artifact_hashes=["a" * 64],
    ) is None
    assert await repository.latest_compatible_checkpoint(
        case_version.version_id,
        policy_version="phase2-v1",
        input_artifact_hashes=["c" * 64],
    ) is None


@pytest.mark.asyncio
async def test_latest_checkpoint_normalizes_input_hash_order(
    repository: SQLiteCaseRepository, case_version: CaseVersionRecord
) -> None:
    checkpoint = CheckpointEnvelope(
        version_id=case_version.version_id,
        stage="acquire_market_data",
        input_artifact_hashes=["b" * 64, "a" * 64],
        output_artifact_hashes=[],
        typed_state_json={},
        policy_version="phase2-v1",
    )
    await repository.save_checkpoint(checkpoint)

    assert await repository.latest_compatible_checkpoint(
        case_version.version_id,
        policy_version="phase2-v1",
        input_artifact_hashes=["a" * 64, "b" * 64],
    ) == checkpoint


@pytest.mark.asyncio
async def test_case_payloads_are_versioned_and_legacy_payloads_remain_readable(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "cases.db"
    legacy = sqlite3.connect(database_path)
    legacy.executescript(
        """
        CREATE TABLE cases (
            case_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, trade_date TEXT NOT NULL,
            mode TEXT NOT NULL, current_version_id TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE case_versions (
            version_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, version_number INTEGER NOT NULL,
            parent_version_id TEXT, status TEXT NOT NULL, outcome TEXT, active_stage TEXT,
            request_json TEXT NOT NULL, report_json TEXT, error TEXT, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE provider_calls (
            provider_call_id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            operation TEXT NOT NULL,
            status TEXT NOT NULL,
            coverage TEXT NOT NULL,
            retrieved_at TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            error_code TEXT,
            source_version TEXT
        );
        """
    )
    now = datetime.now(UTC).isoformat()
    legacy.execute(
        "INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("case-1", "BHP", "2026-08-20", "RECORDED", "version-1", now, now),
    )
    legacy.execute(
        "INSERT INTO case_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "version-1", "case-1", 1, None, "QUEUED", None, None,
            json.dumps({"ticker": "BHP"}), None, None, now, now,
        ),
    )
    legacy.commit()
    legacy.close()

    repository = SQLiteCaseRepository(database_path)
    await repository.initialize()
    await repository.initialize()
    loaded = await repository.get_version("version-1")
    created = await repository.create_version(
        "case-1", parent_version_id="version-1", request_payload={"ticker": "CBA"}
    )

    connection = sqlite3.connect(database_path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(case_versions)")}
    provider_call_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(provider_calls)")
    }
    raw_request = connection.execute(
        "SELECT request_json FROM case_versions WHERE version_id = ?", (created.version_id,)
    ).fetchone()[0]
    connection.close()

    assert loaded.request_payload == {"ticker": "BHP"}
    assert {"request_schema_version", "report_schema_version"}.issubset(columns)
    assert {"artifact_id", "as_of"}.issubset(provider_call_columns)
    assert json.loads(raw_request) == {
        "schema_version": "case-payload-v1",
        "payload": {"ticker": "CBA"},
    }
