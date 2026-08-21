from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from asx_investigator.domain.models import EvidenceItem, EvidenceRole
from asx_investigator.evidence.ingestion import FrozenSource
from asx_investigator.evidence.source_policy import SourcePolicy
from asx_investigator.market.sessions import resolve_session
from asx_investigator.providers.evidence import OfficialEvidenceAcquirer
from asx_investigator.storage.artifacts import ArtifactReference, ArtifactStore


class _FrozenFetcher:
    def __init__(self, frozen: FrozenSource) -> None:
        self.frozen = frozen
        self.calls: list[str] = []

    async def fetch(self, url: str) -> FrozenSource:
        self.calls.append(url)
        return self.frozen


def candidate(url: str) -> EvidenceItem:
    published = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
    return EvidenceItem(
        evidence_id="R1-1",
        source_name="Discovery",
        source_url=url,
        published_at=published,
        retrieved_at=published,
        role=EvidenceRole.CONTEMPORANEOUS_REACTION,
        authority="DISCOVERY_ONLY",
        title="Guidance update",
        passage="Discovery snippet only",
        content_hash="a" * 64,
    )


async def test_approved_issuer_document_is_frozen_and_promoted_from_its_own_timestamp(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path)
    frozen = FrozenSource(
        artifact=ArtifactReference.model_validate(
            store.put(
                b"""<html><head><meta property='article:published_time'
                content='2026-08-20T08:30:00+10:00'></head>
                <body><p>FY26 production guidance increased.</p></body></html>""",
                "text/html",
            ).model_dump()
        ),
        source_url="https://investors.issuer.example/results/guidance.html",
    )
    fetcher = _FrozenFetcher(frozen)
    acquirer = OfficialEvidenceAcquirer(
        store,
        fetcher,
        SourcePolicy({"investors.issuer.example"}),
    )

    promoted = await acquirer.promote(
        candidate("https://investors.issuer.example/results/guidance.html"),
        resolve_session(date(2026, 8, 20)),
        max_document_bytes=400_000,
    )

    assert fetcher.calls == ["https://investors.issuer.example/results/guidance.html"]
    assert promoted is not None
    assert promoted.authority == "PRIMARY_ISSUER"
    assert promoted.role == EvidenceRole.CAUSAL_INPUT
    assert promoted.content_hash == frozen.sha256
    assert "production guidance increased" in promoted.passage


async def test_unapproved_or_untimestamped_document_is_not_promoted(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    frozen = FrozenSource(
        artifact=ArtifactReference.model_validate(
            store.put(b"<html><p>Unverified update.</p></html>", "text/html").model_dump()
        ),
        source_url="https://news.example/update",
    )
    fetcher = _FrozenFetcher(frozen)
    acquirer = OfficialEvidenceAcquirer(store, fetcher, SourcePolicy())

    promoted = await acquirer.promote(
        candidate("https://news.example/update"),
        resolve_session(date(2026, 8, 20)),
        max_document_bytes=400_000,
    )

    assert promoted is None
    assert fetcher.calls == []
