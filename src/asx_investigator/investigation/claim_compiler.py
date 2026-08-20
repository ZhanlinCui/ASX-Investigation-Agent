"""Deterministic publication of claims from registered evidence assertions."""

from __future__ import annotations

from asx_investigator.domain.models import (
    CausalMechanism,
    Claim,
    ClaimType,
    EvidenceAssertion,
)


class ClaimCompilationError(ValueError):
    """Raised when an assertion set cannot safely produce a material claim."""


def _validate_assertion_set(assertions: list[EvidenceAssertion]) -> list[EvidenceAssertion]:
    if not assertions:
        raise ClaimCompilationError("No eligible evidence assertion")
    assertion_ids = [item.assertion_id for item in assertions]
    if len(set(assertion_ids)) != len(assertion_ids):
        raise ClaimCompilationError("Assertion support contains duplicate assertion IDs")
    case_version_ids = {item.case_version_id for item in assertions}
    if len(case_version_ids) != 1:
        raise ClaimCompilationError("Assertion support spans multiple case versions")
    eligible = [item for item in assertions if item.causal_eligible]
    if len(eligible) != len(assertions):
        raise ClaimCompilationError("No eligible evidence assertion")
    return eligible


def compile_claim(
    *,
    ticker: str,
    mechanism: CausalMechanism,
    assertions: list[EvidenceAssertion],
    model_statement: str | None = None,
) -> Claim:
    """Render one safe cause claim while intentionally discarding model prose."""

    del model_statement
    if mechanism == CausalMechanism.UNKNOWN:
        raise ClaimCompilationError("Unknown mechanisms cannot produce a causal claim")
    eligible = _validate_assertion_set(assertions)
    lead = eligible[0]
    supporting_evidence_ids = list(dict.fromkeys(item.evidence_id for item in eligible))
    return Claim(
        claim_id="C1",
        claim_type=ClaimType.CAUSE,
        text=(
            f"{lead.exact_text} This is the leading {mechanism.value.lower()} "
            f"explanation for {ticker}."
        ),
        supporting_evidence_ids=supporting_evidence_ids,
    )
