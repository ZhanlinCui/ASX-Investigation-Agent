from datetime import UTC, datetime, timedelta

import pytest

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
        valid_until=datetime(2027, 1, 1, tzinfo=UTC),
    )

    assert stored.scope == "CONTEXT_ONLY"
    assert (await memory.list_context_facts("BHP"))[0].value == "Materials"


async def test_expired_or_revoked_reference_facts_are_not_context(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()
    expired = await memory.put_reference_fact(
        ticker="BHP",
        field="former_sector",
        value="Legacy",
        source_url="https://issuer.example/profile",
        source_hash="b" * 64,
        valid_until=datetime.now(UTC) - timedelta(seconds=1),
    )
    revoked = await memory.put_reference_fact(
        ticker="BHP",
        field="sector",
        value="Materials",
        source_url="https://issuer.example/profile",
        source_hash="c" * 64,
        valid_until=datetime.now(UTC) + timedelta(days=1),
    )
    await memory.revoke(revoked.entry_id)

    assert expired.entry_id not in {
        fact.entry_id for fact in await memory.list_context_facts("BHP")
    }
    assert await memory.list_context_facts("BHP") == []


async def test_case_claims_and_holdout_labels_cannot_enter_shared_memory(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()

    with pytest.raises(MemoryAdmissionError):
        await memory.put("CASE_CLAIM", {"ticker": "BHP", "claim": "Guidance caused move"})
    with pytest.raises(MemoryAdmissionError):
        await memory.put("HOLDOUT_LABEL", {"case_id": "sealed-1"})
