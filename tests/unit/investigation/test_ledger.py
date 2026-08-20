from datetime import UTC, datetime

import pytest

from asx_investigator.investigation.ledger import LedgerBuilder, LedgerIntegrityError


def test_ledger_appends_hash_bound_entries_in_sequence() -> None:
    ledger = LedgerBuilder()

    entry = ledger.append(
        stage="resolve_instrument",
        status="COMPLETED",
        input_hashes=["b" * 64, "a" * 64, "a" * 64],
        output_hashes=["c" * 64],
        policy_version="phase2-v1",
        model_configuration={"provider": "RECORDED"},
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
    )

    assert entry.sequence == 1
    assert entry.input_hashes == ["a" * 64, "b" * 64]
    assert ledger.entries() == [entry]


def test_ledger_rejects_rewritten_prior_sequence() -> None:
    ledger = LedgerBuilder()
    ledger.append(
        stage="resolve_instrument",
        status="COMPLETED",
        input_hashes=["a" * 64],
        output_hashes=[],
        policy_version="phase2-v1",
        model_configuration={},
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    corrupted = ledger.entries()[0].model_copy(update={"sequence": 2})

    with pytest.raises(LedgerIntegrityError, match="contiguous"):
        LedgerBuilder([corrupted])


def test_ledger_rejects_a_persisted_entry_with_noncanonical_hashes() -> None:
    ledger = LedgerBuilder()
    entry = ledger.append(
        stage="resolve_instrument",
        status="COMPLETED",
        input_hashes=["a" * 64],
        output_hashes=[],
        policy_version="phase2-v1",
        model_configuration={},
        created_at=datetime(2026, 8, 20, tzinfo=UTC),
    ).model_copy(update={"input_hashes": ["not-a-sha256"]})

    with pytest.raises(LedgerIntegrityError, match="SHA-256"):
        LedgerBuilder([entry])
