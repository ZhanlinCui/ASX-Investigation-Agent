from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from asx_investigator.domain.models import (
    CoverageGap,
    EvidenceAssertion,
    EvidenceRole,
    IssuerReferenceFact,
    MarketMove,
    SourceConflict,
)

MAX_EVIDENCE_ITEMS = 12
MAX_CONTEXT_FACTS = 6
MAX_CONTEXT_FACT_SERIALIZED_CHARS = 3_600

_CONTEXT_FIELD_RELEVANCE = {
    "sector": 0,
    "industry": 1,
    "business_description": 2,
    "commodity_exposure": 3,
    "currency_exposure": 4,
}


def _context_sort_key(item: IssuerReferenceFact) -> tuple[int, float, float, str, str]:
    """Rank a ticker's bounded reference facts without learned case conclusions."""

    return (
        _CONTEXT_FIELD_RELEVANCE.get(item.field.lower(), 5),
        -item.valid_from.timestamp(),
        -item.created_at.timestamp(),
        item.field.lower(),
        item.entry_id,
    )


def _serialized_context_size(item: IssuerReferenceFact) -> int:
    return len(json.dumps(item.model_dump(mode="json"), sort_keys=True, separators=(",", ":")))


def select_context_facts(
    facts: list[IssuerReferenceFact],
) -> list[IssuerReferenceFact]:
    """Apply deterministic count and serialized-text bounds before any model call."""

    selected: list[IssuerReferenceFact] = []
    used_characters = 0
    for fact in sorted(facts, key=_context_sort_key):
        if len(selected) >= MAX_CONTEXT_FACTS:
            break
        serialized_size = _serialized_context_size(fact)
        if serialized_size > MAX_CONTEXT_FACT_SERIALIZED_CHARS:
            continue
        if used_characters + serialized_size > MAX_CONTEXT_FACT_SERIALIZED_CHARS:
            continue
        selected.append(fact)
        used_characters += serialized_size
    return selected


class EvidencePacket(BaseModel):
    """The bounded assertion-only payload available to the two model calls."""

    ticker: str
    case_version_id: str
    market_facts: dict[str, float | bool | None]
    assertions: list[EvidenceAssertion] = Field(max_length=MAX_EVIDENCE_ITEMS)
    allowed_assertion_ids: list[str]
    coverage_gaps: list[CoverageGap]
    conflicts: list[SourceConflict]
    context_facts: list[IssuerReferenceFact] = Field(default_factory=list)
    context_as_of: datetime | None = None
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
        if any(item.ticker != self.ticker for item in self.context_facts):
            raise ValueError("Evidence packet context facts must match its ticker")
        if self.context_facts and self.context_as_of is None:
            raise ValueError("Evidence packet context facts require a sealed as-of timestamp")
        if self.context_as_of is not None and self.context_as_of.tzinfo is None:
            raise ValueError("Evidence packet context as-of timestamp must include a timezone")
        if self.context_as_of is not None and any(
            item.valid_until <= self.context_as_of for item in self.context_facts
        ):
            raise ValueError("Evidence packet context facts must be valid at the case cutoff")
        if any(
            item.valid_from > self.context_as_of
            for item in self.context_facts
        ):
            raise ValueError("Evidence packet context facts must be available at the case cutoff")
        if len(self.context_facts) > MAX_CONTEXT_FACTS:
            raise ValueError("Evidence packet context facts exceed the item bound")
        if sum(_serialized_context_size(item) for item in self.context_facts) > (
            MAX_CONTEXT_FACT_SERIALIZED_CHARS
        ):
            raise ValueError("Evidence packet context facts exceed the text bound")
        return self


def build_evidence_packet(
    ticker: str,
    move: MarketMove,
    assertions: list[EvidenceAssertion],
    coverage_gaps: list[CoverageGap],
    conflicts: list[SourceConflict],
    *,
    case_version_id: str,
    context_facts: list[IssuerReferenceFact] | None = None,
    context_as_of: datetime | None = None,
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
        context_facts=select_context_facts(list(context_facts or [])),
        context_as_of=context_as_of,
    )
