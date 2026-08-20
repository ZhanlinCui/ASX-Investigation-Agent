from __future__ import annotations

from pydantic import BaseModel, Field

from asx_investigator.domain.models import (
    CoverageGap,
    EvidenceItem,
    EvidenceRole,
    MarketMove,
    SourceConflict,
)

MAX_EVIDENCE_ITEMS = 12
MAX_PASSAGE_CHARACTERS = 1_800


class EvidenceSnippet(BaseModel):
    evidence_id: str
    source_name: str
    authority: str
    role: EvidenceRole
    published_at: str
    title: str
    passage: str
    locator: str | None = None


class EvidencePacket(BaseModel):
    ticker: str
    market_facts: dict[str, float | bool | None]
    snippets: list[EvidenceSnippet] = Field(max_length=MAX_EVIDENCE_ITEMS)
    allowed_evidence_ids: list[str]
    coverage_gaps: list[CoverageGap]
    conflicts: list[SourceConflict]
    document_content_is_untrusted: bool = True


def build_evidence_packet(
    ticker: str,
    move: MarketMove,
    evidence: list[EvidenceItem],
    coverage_gaps: list[CoverageGap],
    conflicts: list[SourceConflict],
) -> EvidencePacket:
    role_rank = {
        EvidenceRole.CAUSAL_INPUT: 0,
        EvidenceRole.CONTEMPORANEOUS_REACTION: 1,
        EvidenceRole.RETROSPECTIVE_CONTEXT: 2,
        EvidenceRole.EXCLUDED: 3,
    }
    selected = sorted(
        enumerate(evidence),
        key=lambda pair: (role_rank[pair[1].role], pair[0]),
    )[:MAX_EVIDENCE_ITEMS]
    snippets = [
        EvidenceSnippet(
            evidence_id=item.evidence_id,
            source_name=item.source_name,
            authority=item.authority,
            role=item.role,
            published_at=item.published_at.isoformat(),
            title=item.title,
            passage=item.passage[:MAX_PASSAGE_CHARACTERS],
            locator=item.locator,
        )
        for _, item in selected
    ]
    return EvidencePacket(
        ticker=ticker,
        market_facts={
            "close_return_pct": move.close_return_pct,
            "open_gap_pct": move.open_gap_pct,
            "open_to_close_pct": move.open_to_close_pct,
            "turnover_aud": move.turnover_aud,
            "volume_zscore": move.volume_zscore,
            "return_zscore": move.return_zscore,
            "market_relative_return_pct": move.market_relative_return_pct,
            "is_unusual": move.is_unusual,
        },
        snippets=snippets,
        allowed_evidence_ids=[item.evidence_id for item in snippets],
        coverage_gaps=coverage_gaps,
        conflicts=conflicts,
    )
