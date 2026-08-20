from datetime import date, datetime

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
from asx_investigator.investigation.assertions import build_assertions
from asx_investigator.market.sessions import SYDNEY, resolve_session


def evidence(role: EvidenceRole = EvidenceRole.CAUSAL_INPUT) -> EvidenceItem:
    now = datetime(2026, 8, 20, 8, 30, tzinfo=SYDNEY)
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
    assertions = build_assertions(
        [evidence(role)],
        case_version_id="v1",
        session=resolve_session(date(2026, 8, 20)),
    )
    return build_evidence_packet("BHP", move, assertions, [], [], case_version_id="v1")


def proposal(assertion_id: str = "A1") -> HypothesisProposal:
    return HypothesisProposal(
        hypothesis_id="H1",
        rank=1,
        statement="Raised production guidance drove the move.",
        expected_signature="Positive opening gap and elevated volume.",
        supporting_assertion_ids=[assertion_id],
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


def test_unknown_assertion_id_is_rejected() -> None:
    with pytest.raises(ReasoningValidationError, match="unknown assertion"):
        validate_reasoning(HypothesisBatch(hypotheses=[proposal("MADE_UP")]), challenge(), packet())


def test_unrelated_causal_statement_cannot_hide_behind_a_valid_evidence_id() -> None:
    unrelated = proposal().model_copy(
        update={"statement": "A takeover offer from a rival caused the price increase."}
    )
    with pytest.raises(ReasoningValidationError, match="textually supported"):
        validate_reasoning(
            HypothesisBatch(hypotheses=[unrelated]), challenge(), packet()
        )


def test_public_hypothesis_text_is_rebuilt_from_evidence_not_model_prose() -> None:
    injected = proposal().model_copy(
        update={
            "statement": (
                "Production guidance was followed by an unsupported rival takeover offer."
            )
        }
    )
    result = validate_reasoning(
        HypothesisBatch(hypotheses=[injected]), challenge(), packet()
    )

    assert "takeover" not in result.leading.statement.lower()
    assert result.leading.statement == "Production guidance increased before market open."


@pytest.mark.parametrize(
    ("role", "challenge_updates", "message"),
    [
        (EvidenceRole.CONTEMPORANEOUS_REACTION, {}, "non-causal assertion"),
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


def test_duplicate_or_cross_case_assertion_support_is_rejected() -> None:
    duplicate = proposal().model_copy(update={"supporting_assertion_ids": ["A1", "A1"]})
    with pytest.raises(ReasoningValidationError, match="duplicate"):
        validate_reasoning(HypothesisBatch(hypotheses=[duplicate]), challenge(), packet())

    cross_case_packet = packet().model_copy(
        update={"assertions": [packet().assertions[0].model_copy(update={"case_version_id": "v2"})]}
    )
    with pytest.raises(ReasoningValidationError, match="case-scoped"):
        validate_reasoning(HypothesisBatch(hypotheses=[proposal()]), challenge(), cross_case_packet)
