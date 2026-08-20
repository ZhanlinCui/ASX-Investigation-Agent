from datetime import UTC, datetime

import pytest

from asx_investigator.domain.models import CausalMechanism, EvidenceAssertion, EvidenceRole
from asx_investigator.investigation.claim_compiler import (
    ClaimCompilationError,
    compile_claim,
)


def eligible_assertion(
    assertion_id: str, text: str, *, evidence_id: str = "E1"
) -> EvidenceAssertion:
    observed_at = datetime(2026, 8, 20, 8, 30, tzinfo=UTC)
    return EvidenceAssertion(
        assertion_id=assertion_id,
        evidence_id=evidence_id,
        case_version_id="v1",
        exact_text=text,
        span_hash="a" * 64,
        artifact_hash="b" * 64,
        published_at=observed_at,
        retrieved_at=observed_at,
        source_authority="PRIMARY_ISSUER",
        role=EvidenceRole.CAUSAL_INPUT,
        causal_eligible=True,
        mechanism_hint=CausalMechanism.ISSUER_EVENT,
    )


def test_claim_compiler_never_publishes_model_only_text() -> None:
    claim = compile_claim(
        ticker="BHP",
        mechanism=CausalMechanism.ISSUER_EVENT,
        assertions=[eligible_assertion("A1", "BHP raised FY26 production guidance.")],
        model_statement="A takeover offer caused the move.",
    )

    assert "takeover" not in claim.text.lower()
    assert claim.text.startswith("BHP raised FY26 production guidance.")
    assert claim.supporting_evidence_ids == ["E1"]


def test_claim_compiler_rejects_invalid_or_noncausal_assertions() -> None:
    invalid = eligible_assertion("A1", "BHP raised guidance.").model_copy(
        update={"causal_eligible": False}
    )

    with pytest.raises(ClaimCompilationError, match="eligible"):
        compile_claim(
            ticker="BHP",
            mechanism=CausalMechanism.ISSUER_EVENT,
            assertions=[invalid],
        )


def test_claim_compiler_rejects_mechanism_not_bound_to_leading_assertion() -> None:
    unsupported = eligible_assertion("A1", "BHP raised guidance.").model_copy(
        update={"mechanism_hint": CausalMechanism.UNKNOWN}
    )

    with pytest.raises(ClaimCompilationError, match="mechanism"):
        compile_claim(
            ticker="BHP",
            mechanism=CausalMechanism.ISSUER_EVENT,
            assertions=[unsupported],
        )
