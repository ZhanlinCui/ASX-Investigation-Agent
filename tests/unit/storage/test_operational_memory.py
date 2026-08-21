from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from asx_investigator.domain.models import EvidenceItem, EvidenceRole
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus
from asx_investigator.storage.memory import SharedMemoryRepository
from asx_investigator.storage.memory_service import OperationalMemoryService


async def test_operational_memory_admits_only_allowlisted_reference_fields_from_primary_evidence(
    tmp_path: Path,
) -> None:
    memory = SharedMemoryRepository(tmp_path / "memory.db")
    await memory.initialize()
    service = OperationalMemoryService(memory)
    now = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
    evidence = EvidenceItem(
        evidence_id="E1",
        source_name="Issuer IR",
        source_url="https://investors.example/profile",
        published_at=now,
        retrieved_at=now,
        role=EvidenceRole.CAUSAL_INPUT,
        authority="PRIMARY_ISSUER",
        title="Issuer profile",
        passage="Sector: Materials\nCommodity exposure: iron ore\nCase conclusion: buy it",
        content_hash="a" * 64,
    )

    admitted = await service.admit_issuer_reference(
        "BHP", evidence, valid_until=now + timedelta(days=365)
    )

    assert [(item.field, item.value) for item in admitted] == [
        ("sector", "Materials"),
        ("commodity_exposure", "iron ore"),
    ]
    assert all("conclusion" not in item.value for item in admitted)


async def test_provider_health_is_ttl_bound_and_never_part_of_retrieval_context(
    tmp_path: Path,
) -> None:
    memory = SharedMemoryRepository(tmp_path / "memory.db")
    await memory.initialize()
    service = OperationalMemoryService(memory)
    now = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)

    await service.observe_provider_outcome(
        ProviderOutcome(
            status=ProviderStatus.RETRYABLE_FAILURE,
            provider="DISCOVERY",
            retrieved_at=now,
            coverage="NONE",
            error_code="TIMEOUT",
        )
    )

    context = await service.retrieval_context("BHP", now)
    assert context.facts == []
    assert context.unavailable_providers == {"DISCOVERY"}
