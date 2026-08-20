from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from asx_investigator.domain.models import (
    EvidenceRole,
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
    supporting_evidence_ids: list[str] = Field(min_length=1, max_length=12)
    contradicting_evidence_ids: list[str] = Field(default_factory=list, max_length=12)


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


class ValidatedReasoning(BaseModel):
    leading: Hypothesis
    hypotheses: list[Hypothesis]
    validations: list[ValidationResult]
    challenge: ChallengeResult


class InvestigationReasoner(Protocol):
    model_configuration: dict[str, str]

    async def generate(self, packet: EvidencePacket) -> HypothesisBatch: ...

    async def challenge(
        self, packet: EvidencePacket, hypotheses: HypothesisBatch
    ) -> ChallengeResult: ...


def validate_reasoning(
    batch: HypothesisBatch,
    challenge: ChallengeResult,
    packet: EvidencePacket,
) -> ValidatedReasoning:
    allowed = set(packet.allowed_evidence_ids)
    roles = {item.evidence_id: item.role for item in packet.snippets}
    proposals = {item.hypothesis_id: item for item in batch.hypotheses}
    for item in batch.hypotheses:
        referenced = set(item.supporting_evidence_ids + item.contradicting_evidence_ids)
        unknown = sorted(referenced - allowed)
        if unknown:
            raise ReasoningValidationError(
                f"Hypothesis {item.hypothesis_id} references unknown evidence: {unknown}"
            )
    if challenge.leading_hypothesis_id != batch.hypotheses[0].hypothesis_id:
        raise ReasoningValidationError("Challenge did not inspect the rank-one hypothesis")
    if challenge.timing_leakage:
        raise ReasoningValidationError("Challenge detected timing leakage")
    if challenge.unsupported_assumptions:
        raise ReasoningValidationError("Challenge detected unsupported assumptions")
    selected_id = challenge.stronger_alternative_id or challenge.leading_hypothesis_id
    if selected_id not in proposals:
        raise ReasoningValidationError("Challenge selected an unknown stronger alternative")
    selected = proposals[selected_id]
    if not any(
        roles.get(evidence_id) == EvidenceRole.CAUSAL_INPUT
        for evidence_id in selected.supporting_evidence_ids
    ):
        raise ReasoningValidationError(
            "Selected hypothesis has no temporally eligible causal evidence"
        )

    hypotheses: list[Hypothesis] = []
    for proposal in batch.hypotheses:
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
                statement=proposal.statement,
                expected_signature=proposal.expected_signature,
                supporting_evidence_ids=proposal.supporting_evidence_ids,
                contradicting_evidence_ids=proposal.contradicting_evidence_ids,
                validation_ids=["V-EVIDENCE", "V-CHALLENGE"],
            )
        )
    validations = [
        ValidationResult(
            validation_id="V-EVIDENCE",
            kind="EVIDENCE_REFERENTIAL_INTEGRITY",
            status=ValidationStatus.PASS,
            summary="All cited evidence IDs exist and the selected hypothesis has causal input.",
            evidence_ids=selected.supporting_evidence_ids,
        ),
        ValidationResult(
            validation_id="V-CHALLENGE",
            kind="ADVERSARIAL_CHALLENGE",
            status=ValidationStatus.PASS,
            summary=challenge.summary,
            evidence_ids=selected.supporting_evidence_ids,
        ),
    ]
    leading = next(item for item in hypotheses if item.hypothesis_id == selected_id)
    return ValidatedReasoning(
        leading=leading,
        hypotheses=hypotheses,
        validations=validations,
        challenge=challenge,
    )
