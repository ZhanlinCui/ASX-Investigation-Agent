from datetime import UTC, date, datetime
from pathlib import Path

from asx_investigator.domain.models import EvidenceItem, EvidenceRole
from asx_investigator.evidence.registry import SQLiteEvidenceRegistry
from asx_investigator.storage.repository import SQLiteCaseRepository


def item(
    evidence_id: str,
    passage: str,
    content_hash: str,
    *,
    role: EvidenceRole = EvidenceRole.CAUSAL_INPUT,
    authority: str = "PRIMARY_ISSUER",
) -> EvidenceItem:
    now = datetime.now(UTC)
    return EvidenceItem(
        evidence_id=evidence_id,
        source_name="Issuer IR",
        source_url="https://issuer.example/reports/guidance",
        published_at=now,
        retrieved_at=now,
        role=role,
        authority=authority,
        title="Production guidance",
        passage=passage,
        content_hash=content_hash,
        locator="page:1:block:1",
        page=1,
    )


async def test_registry_deduplicates_content_and_searches_exact_passages(
    tmp_path: Path,
) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    await repository.initialize()
    case = await repository.create_case(
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        mode="RECORDED",
        request_payload={"ticker": "BHP"},
    )
    registry = SQLiteEvidenceRegistry(repository.database_path)
    await registry.initialize()

    created = await registry.register(
        case.version_id,
        item("E1", "Production guidance increased for the next financial year.", "same-hash"),
    )
    duplicate = await registry.register(
        case.version_id,
        item("E2", "Syndicated copy of the same document.", "same-hash"),
    )
    await registry.register(
        case.version_id,
        item(
            "E3",
            "Production guidance was discussed after the close.",
            "different-hash",
            role=EvidenceRole.RETROSPECTIVE_CONTEXT,
            authority="MEDIA",
        ),
    )
    results = await registry.search(case.version_id, "production guidance", limit=5)
    primary_only = await registry.search(
        case.version_id,
        "production guidance",
        role=EvidenceRole.CAUSAL_INPUT,
        authority="PRIMARY_ISSUER",
    )
    restored = await registry.get(case.version_id, "E1")

    assert created is True
    assert duplicate is False
    assert {result.evidence_id for result in results} == {"E1", "E3"}
    assert [result.evidence_id for result in primary_only] == ["E1"]
    assert restored.locator == "page:1:block:1"
