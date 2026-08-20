from datetime import datetime

import pytest

from asx_investigator.domain.models import Claim, ClaimType, EvidenceItem, EvidenceRole
from asx_investigator.evidence.validation import CitationValidationError, validate_claims


def _evidence(evidence_id: str, role: EvidenceRole) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        source_name="Issuer IR",
        source_url="https://example.com/release",
        published_at=datetime.fromisoformat("2026-08-20T08:30:00+10:00"),
        retrieved_at=datetime.fromisoformat("2026-08-20T10:30:00+10:00"),
        role=role,
        authority="PRIMARY",
        title="Guidance update",
        passage="The company increased FY26 production guidance.",
        content_hash="abc",
    )


def test_validates_material_claim_with_causal_evidence() -> None:
    claim = Claim(
        claim_id="C1",
        claim_type=ClaimType.CAUSE,
        text="The guidance update was the leading explanation.",
        supporting_evidence_ids=["E1"],
    )

    validate_claims([claim], {"E1": _evidence("E1", EvidenceRole.CAUSAL_INPUT)})


def test_rejects_causal_claim_backed_only_by_retrospective_context() -> None:
    claim = Claim(
        claim_id="C1",
        claim_type=ClaimType.CAUSE,
        text="The media article caused the move.",
        supporting_evidence_ids=["E1"],
    )

    with pytest.raises(CitationValidationError, match="retrospective"):
        validate_claims([claim], {"E1": _evidence("E1", EvidenceRole.RETROSPECTIVE_CONTEXT)})
