from __future__ import annotations

from asx_investigator.domain.models import Claim, ClaimType, EvidenceItem, EvidenceRole


class CitationValidationError(ValueError):
    """Raised when a material claim cannot be released safely."""


def validate_claims(claims: list[Claim], registry: dict[str, EvidenceItem]) -> None:
    material_types = {ClaimType.CAUSE, ClaimType.CONTRIBUTOR, ClaimType.MECHANICAL}
    for claim in claims:
        if claim.claim_type in material_types and not claim.supporting_evidence_ids:
            raise CitationValidationError(f"{claim.claim_id} has no supporting evidence")
        for evidence_id in claim.supporting_evidence_ids:
            evidence = registry.get(evidence_id)
            if evidence is None:
                raise CitationValidationError(
                    f"{claim.claim_id} references missing evidence {evidence_id}"
                )
            if (
                claim.claim_type in material_types
                and evidence.role == EvidenceRole.RETROSPECTIVE_CONTEXT
            ):
                raise CitationValidationError(
                    f"{claim.claim_id} is backed only by retrospective evidence {evidence_id}"
                )
            if evidence.role == EvidenceRole.EXCLUDED:
                raise CitationValidationError(
                    f"{claim.claim_id} uses excluded evidence {evidence_id}"
                )
