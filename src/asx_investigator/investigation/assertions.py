"""Deterministic extraction of case-scoped evidence assertions."""

from __future__ import annotations

import hashlib
import re

from asx_investigator.domain.models import (
    CausalMechanism,
    EvidenceAssertion,
    EvidenceItem,
    EvidenceRole,
    TradingSession,
)
from asx_investigator.market.sessions import classify_event

MAX_ASSERTION_CHARACTERS = 1_800

_MECHANICAL_TERMS = {
    "consolidation",
    "distribution",
    "dividend",
    "reconstruction",
    "split",
}
_CONTEXT_TERMS = {
    "commodity",
    "copper",
    "currency",
    "exchange rate",
    "foreign exchange",
    "index",
    "inflation",
    "interest rate",
    "iron ore",
    "macro",
    "oil",
    "rates",
}


def normalized_hash(value: str) -> str:
    """Return an existing SHA-256 digest unchanged or hash an opaque source value."""

    lowered = value.lower()
    if len(lowered) == 64 and all(character in "0123456789abcdef" for character in lowered):
        return lowered
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def classify_mechanism_hint(
    *, exact_text: str, source_authority: str, source_name: str
) -> CausalMechanism:
    """Classify a bounded assertion span and trusted source metadata only."""

    text = exact_text.lower()
    if any(term in text for term in _MECHANICAL_TERMS):
        return CausalMechanism.MECHANICAL
    source_metadata = f"{source_authority} {source_name}".lower()
    if "issuer" in source_metadata or "investor relations" in source_metadata:
        return CausalMechanism.ISSUER_EVENT
    if any(term in text for term in _CONTEXT_TERMS):
        return CausalMechanism.MACRO_MARKET
    return CausalMechanism.UNKNOWN


def extract_entities(value: str) -> list[str]:
    """Extract stable ticker-like and fiscal-period entities from an exact source span."""

    seen: set[str] = set()
    entities: list[str] = []
    for entity in re.findall(r"\b(?:[A-Z]{2,6}|FY\d{2})\b", value):
        if entity not in seen:
            seen.add(entity)
            entities.append(entity)
    return entities


def extract_numeric_values(value: str) -> dict[str, float]:
    """Extract numeric literals in source order without assigning causal meaning."""

    values: dict[str, float] = {}
    for index, match in enumerate(re.finditer(r"(?<![A-Za-z])\d+(?:\.\d+)?", value), start=1):
        values[f"value_{index}"] = float(match.group())
    return values


def build_assertions(
    evidence: list[EvidenceItem], *, case_version_id: str, session: TradingSession
) -> list[EvidenceAssertion]:
    """Freeze bounded extractive assertions for one case version and ASX session."""

    assertions: list[EvidenceAssertion] = []
    for index, item in enumerate(evidence, start=1):
        exact_text = item.passage[:MAX_ASSERTION_CHARACTERS]
        timing = classify_event(item.published_at, session)
        assertions.append(
            EvidenceAssertion(
                assertion_id=f"A{index}",
                evidence_id=item.evidence_id,
                case_version_id=case_version_id,
                exact_text=exact_text,
                span_hash=hashlib.sha256(exact_text.encode("utf-8")).hexdigest(),
                artifact_hash=normalized_hash(item.content_hash),
                published_at=item.published_at,
                retrieved_at=item.retrieved_at,
                source_authority=item.authority,
                locator=item.locator,
                role=item.role,
                causal_eligible=(
                    item.role == EvidenceRole.CAUSAL_INPUT and timing.eligible_same_day_cause
                ),
                mechanism_hint=classify_mechanism_hint(
                    exact_text=exact_text,
                    source_authority=item.authority,
                    source_name=item.source_name,
                ),
                normalized_entities=extract_entities(exact_text),
                normalized_values=extract_numeric_values(exact_text),
            )
        )
    return assertions
