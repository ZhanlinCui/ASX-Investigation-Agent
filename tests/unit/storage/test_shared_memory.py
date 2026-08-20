from datetime import UTC, datetime, timedelta

import pytest

from asx_investigator.confidence.calibration import (
    CalibrationRecord,
    build_calibration_artifact,
    review_calibration_artifact,
)
from asx_investigator.storage.memory import (
    MemoryAdmissionError,
    SharedMemoryRepository,
)


async def test_only_expiring_provenanced_reference_facts_are_admitted(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()

    stored = await memory.put_reference_fact(
        ticker="BHP",
        field="sector",
        value="Materials",
        source_url="https://issuer.example/profile",
        source_hash="a" * 64,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2027, 1, 1, tzinfo=UTC),
    )

    assert stored.scope == "CONTEXT_ONLY"
    assert (
        await memory.list_context_facts(
            "BHP", as_of=datetime(2026, 8, 20, tzinfo=UTC)
        )
    )[0].value == "Materials"


async def test_expired_or_revoked_reference_facts_are_not_context(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()
    expired = await memory.put_reference_fact(
        ticker="BHP",
        field="former_sector",
        value="Legacy",
        source_url="https://issuer.example/profile",
        source_hash="b" * 64,
        valid_from=datetime.now(UTC) - timedelta(days=2),
        valid_until=datetime.now(UTC) - timedelta(seconds=1),
    )
    revoked = await memory.put_reference_fact(
        ticker="BHP",
        field="sector",
        value="Materials",
        source_url="https://issuer.example/profile",
        source_hash="c" * 64,
        valid_from=datetime.now(UTC) - timedelta(days=1),
        valid_until=datetime.now(UTC) + timedelta(days=1),
    )
    await memory.revoke(revoked.entry_id)

    assert expired.entry_id not in {
        fact.entry_id
        for fact in await memory.list_context_facts("BHP", as_of=datetime.now(UTC))
    }
    assert await memory.list_context_facts("BHP", as_of=datetime.now(UTC)) == []


async def test_case_claims_and_holdout_labels_cannot_enter_shared_memory(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()

    with pytest.raises(MemoryAdmissionError):
        await memory.put("CASE_CLAIM", {"ticker": "BHP", "claim": "Guidance caused move"})
    with pytest.raises(MemoryAdmissionError):
        await memory.put("HOLDOUT_LABEL", {"case_id": "sealed-1"})


async def test_reference_fact_requires_point_in_time_availability(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()

    with pytest.raises(MemoryAdmissionError, match="availability"):
        await memory.put_reference_fact(
            ticker="BHP",
            field="sector",
            value="Materials",
            source_url="https://issuer.example/profile",
            source_hash="d" * 64,
            valid_until=datetime(2027, 1, 1, tzinfo=UTC),
        )


async def test_typed_internal_memory_rejects_unknown_and_nested_payloads(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()
    active_until = datetime(2027, 1, 1, tzinfo=UTC)

    with pytest.raises(MemoryAdmissionError, match="unknown|nested"):
        await memory.put(
            "PROVIDER_HEALTH",
            {
                "provider": "EODHD",
                "status": "SUCCESS",
                "source_hash": "e" * 64,
                "source_url": "provider://EODHD",
                "observed_at": datetime(2026, 8, 20, tzinfo=UTC),
                "valid_until": active_until,
                "details": {"parent_conclusion": "Guidance caused the move"},
            },
        )
    with pytest.raises(MemoryAdmissionError, match="nested"):
        await memory.put(
            "PROVIDER_HEALTH",
            {
                "provider": "EODHD",
                "status": {"parent_conclusion": "Guidance caused the move"},
                "source_hash": "e" * 64,
                "source_url": "provider://EODHD",
                "observed_at": datetime(2026, 8, 20, tzinfo=UTC),
                "valid_until": active_until,
            },
        )
    with pytest.raises(MemoryAdmissionError, match="reviewed"):
        await memory.put(
            "CALIBRATION_ARTIFACT",
            {
                "calibration_version": "calibration-v1",
                "rule_version": "confidence-v1",
                "artifact_hash": "f" * 64,
                "rule_hash": "a" * 64,
                "valid_from": datetime(2026, 8, 20, tzinfo=UTC),
                "valid_until": active_until,
                "rules": {"sealed_holdout_label": "EXPLAINED"},
            },
        )
    with pytest.raises(MemoryAdmissionError, match="reviewed"):
        await memory.put(
            "CALIBRATION_ARTIFACT",
            {
                "calibration_version": "calibration-v1",
                "rule_version": {"case_claim": "Guidance caused the move"},
                "artifact_hash": "f" * 64,
                "rule_hash": "a" * 64,
                "valid_from": datetime(2026, 8, 20, tzinfo=UTC),
                "valid_until": active_until,
            },
        )


async def test_typed_internal_memory_keeps_only_provider_and_calibration_metadata(
    tmp_path,
) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()
    valid_from = datetime(2026, 8, 20, tzinfo=UTC)
    valid_until = datetime(2027, 1, 1, tzinfo=UTC)

    health = await memory.record_provider_health(
        provider="EODHD",
        status="SUCCESS",
        source_hash="3" * 64,
        observed_at=valid_from,
        valid_until=valid_until,
    )
    artifact = build_calibration_artifact(
        records=[
            CalibrationRecord(
                case_id=f"case-{index}", confidence_band="HIGH", correct=True
            )
            for index in range(5)
        ],
        corpus_version="gold-dev-v1",
        confidence_rule_version="confidence-v1",
    )
    reviewed = review_calibration_artifact(
        artifact,
        reviewer="evaluation-reviewer",
        reviewed_at=valid_from,
        creation_commit="abcdef1",
    )
    calibration = await memory.record_calibration_artifact(
        artifact=reviewed,
        rule_hash="5" * 64,
        valid_from=valid_from,
        valid_until=valid_until,
    )

    assert health.payload == {"provider": "EODHD", "status": "SUCCESS"}
    assert calibration.payload == {
        "calibration_version": "confidence-calibration-v1",
        "rule_version": "confidence-v1",
        "rule_hash": "5" * 64,
    }


async def test_unreviewed_calibration_artifacts_cannot_use_the_generic_memory_path(
    tmp_path,
) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()

    with pytest.raises(MemoryAdmissionError, match="reviewed"):
        await memory.put(
            "CALIBRATION_ARTIFACT",
            {
                "calibration_version": "confidence-calibration-v1",
                "rule_version": "confidence-v1",
                "artifact_hash": "4" * 64,
                "rule_hash": "5" * 64,
                "valid_from": datetime(2026, 8, 20, tzinfo=UTC),
                "valid_until": datetime(2027, 1, 1, tzinfo=UTC),
            },
        )


async def test_context_facts_are_selected_as_of_case_cutoff_not_wall_clock(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()
    cutoff = datetime(2026, 8, 20, 16, 0, tzinfo=UTC)
    historical = await memory.put_reference_fact(
        ticker="BHP",
        field="sector",
        value="Materials",
        source_url="https://issuer.example/profile",
        source_hash="1" * 64,
        valid_from=cutoff - timedelta(days=1),
        valid_until=cutoff + timedelta(days=1),
    )
    await memory.put_reference_fact(
        ticker="BHP",
        field="new_sector",
        value="Future-only fact",
        source_url="https://issuer.example/new-profile",
        source_hash="2" * 64,
        valid_from=cutoff + timedelta(minutes=1),
        valid_until=cutoff + timedelta(days=2),
    )

    facts = await memory.list_context_facts("BHP", as_of=cutoff)

    assert [fact.entry_id for fact in facts] == [historical.entry_id]
