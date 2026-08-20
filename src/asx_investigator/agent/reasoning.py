from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from asx_investigator.domain.models import (
    EvidenceAssertion,
    Hypothesis,
    HypothesisStatus,
    ValidationResult,
    ValidationStatus,
)
from asx_investigator.evidence.context import EvidencePacket


class ReasoningUnavailable(RuntimeError):
    """The bounded model operation could not produce a valid structured result."""


class ReasoningValidationError(ValueError):
    """A model result violated deterministic publication rules."""


class EvidenceGapRequest(BaseModel):
    purpose: str = Field(min_length=10, max_length=240)
    query: str = Field(min_length=3, max_length=240)


class HypothesisProposal(BaseModel):
    hypothesis_id: str = Field(pattern=r"^H[1-5]$")
    rank: int = Field(ge=1, le=5)
    driver_label: str = Field(default="UNCLASSIFIED", min_length=3, max_length=80)
    statement: str = Field(min_length=10, max_length=520)
    expected_signature: str = Field(min_length=5, max_length=300)
    supporting_assertion_ids: list[str] = Field(min_length=1, max_length=12)
    contradicting_assertion_ids: list[str] = Field(default_factory=list, max_length=12)


class HypothesisBatch(BaseModel):
    hypotheses: list[HypothesisProposal] = Field(min_length=1, max_length=5)
    evidence_gap: EvidenceGapRequest | None = None

    @model_validator(mode="after")
    def validate_rank_order(self) -> HypothesisBatch:
        ranks = [item.rank for item in self.hypotheses]
        identifiers = [item.hypothesis_id for item in self.hypotheses]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("hypothesis ranks must be ordered and contiguous")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("hypothesis IDs must be unique")
        return self


class ChallengeResult(BaseModel):
    leading_hypothesis_id: str = Field(pattern=r"^H[1-5]$")
    stronger_alternative_id: str | None = Field(default=None, pattern=r"^H[1-5]$")
    timing_leakage: bool
    unsupported_assumptions: list[str] = Field(default_factory=list, max_length=10)
    summary: str = Field(min_length=10, max_length=520)
    accepted_targeted_assertion_ids: list[str] = Field(default_factory=list, max_length=12)


class ValidatedReasoning(BaseModel):
    leading: Hypothesis
    leading_assertion_ids: list[str]
    hypotheses: list[Hypothesis]
    validations: list[ValidationResult]
    challenge: ChallengeResult


class InvestigationReasoner(Protocol):
    model_configuration: dict[str, str]

    async def generate(self, packet: EvidencePacket) -> HypothesisBatch: ...

    async def challenge(
        self, packet: EvidencePacket, hypotheses: HypothesisBatch
    ) -> ChallengeResult: ...


_NON_EVIDENTIAL_WORDS = {
    "caused",
    "company",
    "drove",
    "leading",
    "market",
    "move",
    "price",
    "share",
    "stock",
}


def _meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 4 and token not in _NON_EVIDENTIAL_WORDS
    }


def _unique_ids(values: list[str], *, label: str, hypothesis_id: str) -> None:
    if len(set(values)) != len(values):
        raise ReasoningValidationError(
            f"Hypothesis {hypothesis_id} contains duplicate {label} assertion IDs"
        )


def _evidence_ids(assertions: list[EvidenceAssertion]) -> list[str]:
    return list(dict.fromkeys(item.evidence_id for item in assertions))


def validate_reasoning(
    batch: HypothesisBatch,
    challenge: ChallengeResult,
    packet: EvidencePacket,
    *,
    targeted_assertion_ids: set[str] | None = None,
) -> ValidatedReasoning:
    allowed = set(packet.allowed_assertion_ids)
    assertion_by_id = {item.assertion_id: item for item in packet.assertions}
    if len(assertion_by_id) != len(packet.assertions) or any(
        item.case_version_id != packet.case_version_id for item in packet.assertions
    ):
        raise ReasoningValidationError("Packet assertions are not uniquely case-scoped")
    proposals = {item.hypothesis_id: item for item in batch.hypotheses}
    targeted = targeted_assertion_ids or set()
    for item in batch.hypotheses:
        referenced = item.supporting_assertion_ids + item.contradicting_assertion_ids
        _unique_ids(referenced, label="referenced", hypothesis_id=item.hypothesis_id)
        unknown = sorted(set(referenced) - allowed)
        if unknown:
            raise ReasoningValidationError(
                f"Hypothesis {item.hypothesis_id} references unknown assertion: {unknown}"
            )
        supporting = [
            assertion_by_id[assertion_id] for assertion_id in item.supporting_assertion_ids
        ]
        if not all(assertion.causal_eligible for assertion in supporting):
            raise ReasoningValidationError(
                f"Hypothesis {item.hypothesis_id} has non-causal assertion support"
            )
    if challenge.leading_hypothesis_id != batch.hypotheses[0].hypothesis_id:
        raise ReasoningValidationError("Challenge did not inspect the rank-one hypothesis")
    if challenge.timing_leakage:
        raise ReasoningValidationError("Challenge detected timing leakage")
    if challenge.unsupported_assumptions:
        raise ReasoningValidationError("Challenge detected unsupported assumptions")
    accepted_targets = challenge.accepted_targeted_assertion_ids
    _unique_ids(accepted_targets, label="targeted", hypothesis_id="challenge")
    unknown_targets = sorted(set(accepted_targets) - allowed)
    if unknown_targets:
        raise ReasoningValidationError(
            f"Challenge accepted unknown targeted assertion: {unknown_targets}"
        )
    unfrozen_targets = sorted(set(accepted_targets) - targeted)
    if unfrozen_targets:
        raise ReasoningValidationError(
            "Challenge accepted assertion that is not a retrieved targeted item: "
            f"{unfrozen_targets}"
        )
    noncausal_targets = [
        assertion_id
        for assertion_id in accepted_targets
        if not assertion_by_id[assertion_id].causal_eligible
    ]
    if noncausal_targets:
        raise ReasoningValidationError(
            "Challenge accepted targeted assertion that is not causal input: "
            f"{noncausal_targets}"
        )
    selected_id = challenge.stronger_alternative_id or challenge.leading_hypothesis_id
    if selected_id not in proposals:
        raise ReasoningValidationError("Challenge selected an unknown stronger alternative")
    selected = proposals[selected_id]
    selected_assertion_ids = list(
        dict.fromkeys(selected.supporting_assertion_ids + accepted_targets)
    )
    if set(selected_assertion_ids) & set(selected.contradicting_assertion_ids):
        raise ReasoningValidationError(
            "Selected hypothesis has contradiction-only assertion support"
        )
    selected_assertions = [assertion_by_id[assertion_id] for assertion_id in selected_assertion_ids]
    if not selected_assertions or not all(item.causal_eligible for item in selected_assertions):
        raise ReasoningValidationError(
            "Selected hypothesis has no temporally eligible causal assertion"
        )
    supporting_text = " ".join(item.exact_text for item in selected_assertions)
    statement_tokens = _meaningful_tokens(selected.statement)
    overlap = statement_tokens & _meaningful_tokens(supporting_text)
    required_overlap = 1 if len(statement_tokens) <= 1 else 2
    if len(overlap) < required_overlap:
        raise ReasoningValidationError(
            "Selected hypothesis is not textually supported by its cited assertions"
        )

    hypotheses: list[Hypothesis] = []
    for proposal in batch.hypotheses:
        support_ids = (
            selected_assertion_ids
            if proposal.hypothesis_id == selected_id
            else proposal.supporting_assertion_ids
        )
        cited = [assertion_by_id[assertion_id] for assertion_id in support_ids]
        contradictions = [
            assertion_by_id[assertion_id]
            for assertion_id in proposal.contradicting_assertion_ids
        ]
        safe_statement = " ".join(item.exact_text for item in cited)[:520]
        hypotheses.append(
            Hypothesis(
                hypothesis_id=proposal.hypothesis_id,
                rank=proposal.rank,
                status=(
                    HypothesisStatus.LEADING
                    if proposal.hypothesis_id == selected_id
                    else HypothesisStatus.ALTERNATIVE
                ),
                driver_label=proposal.driver_label,
                statement=safe_statement,
                expected_signature=proposal.expected_signature,
                supporting_evidence_ids=_evidence_ids(cited),
                contradicting_evidence_ids=_evidence_ids(contradictions),
                validation_ids=["V-EVIDENCE", "V-CHALLENGE"],
            )
        )
    selected_evidence_ids = _evidence_ids(selected_assertions)
    validations = [
        ValidationResult(
            validation_id="V-EVIDENCE",
            kind="ASSERTION_REFERENTIAL_INTEGRITY",
            status=ValidationStatus.PASS,
            summary=(
                "All cited assertion IDs are case-scoped and time-eligible; published "
                "hypothesis text is reconstructed from exact assertion spans."
            ),
            evidence_ids=selected_evidence_ids,
        ),
        ValidationResult(
            validation_id="V-CHALLENGE",
            kind="ADVERSARIAL_CHALLENGE",
            status=ValidationStatus.PASS,
            summary=challenge.summary,
            evidence_ids=selected_evidence_ids,
        ),
    ]
    leading = next(item for item in hypotheses if item.hypothesis_id == selected_id)
    return ValidatedReasoning(
        leading=leading,
        leading_assertion_ids=selected_assertion_ids,
        hypotheses=hypotheses,
        validations=validations,
        challenge=challenge,
    )
