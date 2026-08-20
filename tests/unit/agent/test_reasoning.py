from datetime import UTC, datetime

import pytest

from asx_investigator.agent.reasoning import (
    ChallengeResult,
    HypothesisBatch,
    HypothesisProposal,
    ReasoningValidationError,
    validate_reasoning,
)
from asx_investigator.domain.models import EvidenceItem, EvidenceRole, MarketMove
from asx_investigator.evidence.context import build_evidence_packet


def evidence(role: EvidenceRole = EvidenceRole.CAUSAL_INPUT) -> EvidenceItem:
    now = datetime.now(UTC)
    return EvidenceItem(
        evidence_id="E1",
        source_name="Issuer IR",
        source_url="https://issuer.example/update",
        published_at=now,
        retrieved_at=now,
        role=role,
        authority="PRIMARY_ISSUER",
        title="Guidance update",
        passage="Production guidance increased before market open.",
        content_hash="hash-1",
    )


def packet(role: EvidenceRole = EvidenceRole.CAUSAL_INPUT):
    move = MarketMove(
        close_return_pct=8,
        open_gap_pct=6,
        open_to_close_pct=1.9,
        turnover_aud=8_000_000,
        volume_zscore=4,
        return_zscore=5,
        market_relative_return_pct=7,
        is_unusual=True,
    )
    return build_evidence_packet("BHP", move, [evidence(role)], [], [])


def proposal(evidence_id: str = "E1") -> HypothesisProposal:
    return HypothesisProposal(
        hypothesis_id="H1",
        rank=1,
        statement="Raised production guidance drove the move.",
        expected_signature="Positive opening gap and elevated volume.",
        supporting_evidence_ids=[evidence_id],
    )


def challenge(**updates: object) -> ChallengeResult:
    values: dict[str, object] = {
        "leading_hypothesis_id": "H1",
        "stronger_alternative_id": None,
        "timing_leakage": False,
        "unsupported_assumptions": [],
        "summary": "No stronger evidence-backed alternative was identified.",
    }
    values.update(updates)
    return ChallengeResult.model_validate(values)


def test_valid_reasoning_is_converted_to_claim_safe_hypotheses() -> None:
    result = validate_reasoning(
        HypothesisBatch(hypotheses=[proposal()]), challenge(), packet()
    )

    assert result.leading.hypothesis_id == "H1"
    assert result.leading.supporting_evidence_ids == ["E1"]
    assert result.validations[0].status == "PASS"


def test_unknown_evidence_id_is_rejected() -> None:
    with pytest.raises(ReasoningValidationError, match="unknown evidence"):
        validate_reasoning(
            HypothesisBatch(hypotheses=[proposal("MADE_UP")]), challenge(), packet()
        )


@pytest.mark.parametrize(
    ("role", "challenge_updates", "message"),
    [
        (EvidenceRole.CONTEMPORANEOUS_REACTION, {}, "causal evidence"),
        (EvidenceRole.CAUSAL_INPUT, {"timing_leakage": True}, "timing leakage"),
        (
            EvidenceRole.CAUSAL_INPUT,
            {"unsupported_assumptions": ["Commodity price rose"]},
            "unsupported assumptions",
        ),
    ],
)
def test_noncausal_or_leaky_reasoning_is_rejected(
    role: EvidenceRole, challenge_updates: dict[str, object], message: str
) -> None:
    with pytest.raises(ReasoningValidationError, match=message):
        validate_reasoning(
            HypothesisBatch(hypotheses=[proposal()]),
            challenge(**challenge_updates),
            packet(role),
        )
