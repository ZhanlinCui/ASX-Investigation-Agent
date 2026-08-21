"""Secure promotion of discovered candidates into frozen primary evidence."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Protocol

import httpx

from asx_investigator.domain.models import EvidenceItem, TradingSession
from asx_investigator.evidence.ingestion import FrozenSource
from asx_investigator.evidence.parsing import parse_source
from asx_investigator.evidence.source_policy import SourcePolicy
from asx_investigator.storage.artifacts import ArtifactStore


class OfficialSourceFetcher(Protocol):
    async def fetch(self, url: str) -> FrozenSource: ...


_PUBLISHED_META_PATTERNS = (
    re.compile(
        r"<meta[^>]+(?:property|name)=[\"'](?:article:published_time|datePublished)[\"']"
        r"[^>]+content=[\"']([^\"']+)[\"']",
        re.IGNORECASE,
    ),
    re.compile(
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+(?:property|name)="
        r"[\"'](?:article:published_time|datePublished)[\"']",
        re.IGNORECASE,
    ),
    re.compile(r"<time[^>]+datetime=[\"']([^\"']+)[\"']", re.IGNORECASE),
)


def document_published_at(content: bytes, mime_type: str) -> datetime | None:
    """Extract only an explicit source timestamp; discovery metadata is insufficient."""

    if mime_type != "text/html":
        return None
    text = content.decode("utf-8", errors="replace")
    for pattern in _PUBLISHED_META_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        try:
            value = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
        except ValueError:
            continue
        if value.tzinfo is not None:
            return value
    return None


class OfficialEvidenceAcquirer:
    """Promote only approved, frozen and independently timestamped documents."""

    def __init__(
        self,
        artifacts: ArtifactStore,
        fetcher: OfficialSourceFetcher,
        source_policy: SourcePolicy,
    ) -> None:
        self.artifacts = artifacts
        self.fetcher = fetcher
        self.source_policy = source_policy

    async def promote(
        self,
        candidate: EvidenceItem,
        session: TradingSession,
        *,
        max_document_bytes: int,
    ) -> EvidenceItem | None:
        """Return a primary/context item only when document bytes prove its timing."""

        candidate_decision = self.source_policy.decide(
            candidate.source_url, candidate.published_at, session
        )
        if candidate_decision.authority not in {"PRIMARY_ISSUER", "APPROVED_OFFICIAL"}:
            return None
        frozen = await self.fetcher.fetch(candidate.source_url)
        if frozen.size_bytes > max_document_bytes:
            return None
        content = self.artifacts.get(frozen.artifact_id)
        published_at = document_published_at(content, frozen.mime_type)
        if published_at is None:
            return None
        decision = self.source_policy.decide(candidate.source_url, published_at, session)
        if decision.authority not in {"PRIMARY_ISSUER", "APPROVED_OFFICIAL"}:
            return None
        passages = parse_source(content, frozen.mime_type)
        if not passages:
            return None
        passage = passages[0]
        host = httpx.URL(candidate.source_url).host or "Approved source"
        return EvidenceItem(
            evidence_id=f"{candidate.evidence_id}-P",
            source_name=host,
            source_url=candidate.source_url,
            published_at=published_at,
            retrieved_at=candidate.retrieved_at,
            role=decision.evidence_role,
            authority=decision.authority,
            title=candidate.title,
            passage=passage.text,
            content_hash=frozen.sha256,
            page=passage.page,
            locator=f"{passage.locator};artifact={frozen.artifact_id}",
        )
