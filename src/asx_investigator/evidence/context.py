from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from asx_investigator.domain.models import (
    CoverageGap,
    EvidenceAssertion,
    EvidenceRole,
    MarketMove,
    SourceConflict,
)

MAX_EVIDENCE_ITEMS = 12


class EvidencePacket(BaseModel):
    """The bounded assertion-only payload available to the two model calls."""

    ticker: str
    case_version_id: str
    market_facts: dict[str, float | bool | None]
    assertions: list[EvidenceAssertion] = Field(max_length=MAX_EVIDENCE_ITEMS)
    allowed_assertion_ids: list[str]
    coverage_gaps: list[CoverageGap]
    conflicts: list[SourceConflict]
    document_content_is_untrusted: bool = True

    @model_validator(mode="after")
    def validate_case_bound_assertions(self) -> EvidencePacket:
        assertion_ids = [item.assertion_id for item in self.assertions]
        if len(set(assertion_ids)) != len(assertion_ids):
            raise ValueError("Evidence packet contains duplicate assertion IDs")
        if any(item.case_version_id != self.case_version_id for item in self.assertions):
            raise ValueError("Evidence packet assertions must be case-scoped")
        if self.allowed_assertion_ids != assertion_ids:
            raise ValueError("Evidence packet allowed assertion IDs must match its assertions")
        return self


def build_evidence_packet(
    ticker: str,
    move: MarketMove,
    assertions: list[EvidenceAssertion],
    coverage_gaps: list[CoverageGap],
    conflicts: list[SourceConflict],
    *,
    case_version_id: str,
) -> EvidencePacket:
    """Bound case-scoped assertions using the established deterministic role ordering."""

    role_rank = {
        EvidenceRole.CAUSAL_INPUT: 0,
        EvidenceRole.CONTEMPORANEOUS_REACTION: 1,
        EvidenceRole.RETROSPECTIVE_CONTEXT: 2,
        EvidenceRole.EXCLUDED: 3,
    }
    selected = sorted(
        enumerate(assertions),
        key=lambda pair: (role_rank[pair[1].role], pair[0]),
    )[:MAX_EVIDENCE_ITEMS]
    packet_assertions = [item for _, item in selected]
    return EvidencePacket(
        ticker=ticker,
        case_version_id=case_version_id,
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
        assertions=packet_assertions,
        allowed_assertion_ids=[item.assertion_id for item in packet_assertions],
        coverage_gaps=coverage_gaps,
        conflicts=conflicts,
    )
