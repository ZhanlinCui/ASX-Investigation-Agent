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


def _evidence(evidence_id: str, role: EvidenceRole = EvidenceRole.CAUSAL_INPUT) -> EvidenceItem:
    now = datetime(2026, 8, 20, 8, 30, tzinfo=SYDNEY)
    return EvidenceItem(
        evidence_id=evidence_id,
        source_name="Issuer IR",
        source_url=f"https://issuer.example/{evidence_id}",
        published_at=now,
        retrieved_at=now,
        role=role,
        authority="PRIMARY_ISSUER",
        title=f"Guidance update {evidence_id}",
        passage="Production guidance increased before market open.",
        content_hash=f"hash-{evidence_id}",
    )


def _packet(*evidence: EvidenceItem):
    return build_evidence_packet(
        "BHP",
        MarketMove(
            close_return_pct=8,
            open_gap_pct=6,
            open_to_close_pct=1.9,
            turnover_aud=8_000_000,
            volume_zscore=4,
            return_zscore=5,
            market_relative_return_pct=7,
            is_unusual=True,
        ),
        build_assertions(
            list(evidence),
            case_version_id="v1",
            session=resolve_session(date(2026, 8, 20)),
        ),
        [],
        [],
        case_version_id="v1",
    )


def _batch() -> HypothesisBatch:
    return HypothesisBatch(
        hypotheses=[
            HypothesisProposal(
                hypothesis_id="H1",
                rank=1,
                statement="Raised production guidance drove the move.",
                expected_signature="Positive opening gap and elevated volume.",
                supporting_assertion_ids=["A1"],
            )
        ]
    )


def _challenge(**updates: object) -> ChallengeResult:
    values: dict[str, object] = {
        "leading_hypothesis_id": "H1",
        "timing_leakage": False,
        "unsupported_assumptions": [],
        "summary": "The targeted issuer release confirms the supplied announcement.",
        "accepted_targeted_assertion_ids": ["A2"],
    }
    values.update(updates)
    return ChallengeResult.model_validate(values)


def test_challenge_can_add_only_a_frozen_targeted_causal_evidence_id() -> None:
    result = validate_reasoning(
        _batch(),
        _challenge(),
        _packet(_evidence("E1"), _evidence("T1")),
        targeted_assertion_ids={"A2"},
    )

    assert result.leading.supporting_evidence_ids == ["E1", "T1"]
    assert result.validations[0].evidence_ids == ["E1", "T1"]


@pytest.mark.parametrize(
    ("accepted_ids", "targeted_ids", "target_role", "message"),
    [
        (["A2"], set(), EvidenceRole.CAUSAL_INPUT, "not a retrieved targeted"),
        (["UNKNOWN"], {"A2"}, EvidenceRole.CAUSAL_INPUT, "unknown targeted"),
        (["A2"], {"A2"}, EvidenceRole.CONTEMPORANEOUS_REACTION, "causal input"),
    ],
)
def test_challenge_rejects_unfrozen_unknown_or_noncausal_targeted_evidence(
    accepted_ids: list[str],
    targeted_ids: set[str],
    target_role: EvidenceRole,
    message: str,
) -> None:
    evidence = [_evidence("E1"), _evidence("T1", target_role)]
    with pytest.raises(ReasoningValidationError, match=message):
        validate_reasoning(
            _batch(),
            _challenge(accepted_targeted_assertion_ids=accepted_ids),
            _packet(*evidence),
            targeted_assertion_ids=targeted_ids,
        )
