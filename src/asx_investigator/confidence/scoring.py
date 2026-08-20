from __future__ import annotations

from dataclasses import dataclass

from asx_investigator.domain.models import (
    Claim,
    ClaimSupportAssessment,
    ConfidenceAssessment,
    EvidenceItem,
)

ACTIVE_CONFIDENCE_RULE_VERSION = "confidence-v1"


@dataclass(frozen=True)
class ConfidenceFeatures:
    source_authority: float
    temporal_eligibility: float
    market_signature_fit: float
    quantitative_consistency: float
    independent_corroboration: float
    coverage_completeness: float
    contradiction_strength: float = 0.0
    alternative_strength: float = 0.0
    has_primary_evidence: bool = True
    disclosure_coverage_complete: bool = True
    has_material_conflict: bool = False
    timing_resolved: bool = True
    needs_intraday_data: bool = False
    has_intraday_data: bool = False


def score_confidence(features: ConfidenceFeatures) -> ConfidenceAssessment:
    raw = (
        features.source_authority * 0.2
        + features.temporal_eligibility * 0.2
        + features.market_signature_fit * 0.2
        + features.quantitative_consistency * 0.15
        + features.independent_corroboration * 0.1
        + features.coverage_completeness * 0.15
        - features.contradiction_strength * 0.2
        - features.alternative_strength * 0.15
    )
    score = max(0.0, min(1.0, raw))
    caps: list[str] = []
    if not features.has_primary_evidence:
        score = min(score, 0.70)
        caps.append("NO_PRIMARY_EVIDENCE")
    if not features.disclosure_coverage_complete:
        score = min(score, 0.65)
        caps.append("DISCLOSURE_COVERAGE_PARTIAL")
    if features.has_material_conflict:
        score = min(score, 0.60)
        caps.append("MATERIAL_CONFLICT")
    if not features.timing_resolved:
        score = min(score, 0.60)
        caps.append("TIMING_UNRESOLVED")
    if features.needs_intraday_data and not features.has_intraday_data:
        score = min(score, 0.65)
        caps.append("INTRADAY_DATA_MISSING")
    score = round(score, 2)
    band = "HIGH" if score >= 0.75 else "MEDIUM" if score >= 0.45 else "LOW"
    positive_factors: list[str] = []
    if features.has_primary_evidence:
        positive_factors.append("Temporally eligible primary evidence")
    if features.independent_corroboration >= 0.5:
        positive_factors.append("Independent corroboration")
    if features.market_signature_fit >= 0.7:
        positive_factors.append("Market signature fit")
    return ConfidenceAssessment(
        score=score,
        band=band,
        rule_version=ACTIVE_CONFIDENCE_RULE_VERSION,
        positive_factors=positive_factors,
        negative_factors=caps.copy(),
        applied_caps=caps,
    )


def assess_claim_support(
    claim: Claim,
    evidence_registry: dict[str, EvidenceItem],
) -> ClaimSupportAssessment:
    supporting = [
        evidence_registry[item]
        for item in claim.supporting_evidence_ids
        if item in evidence_registry
    ]
    primary_authorities = {
        "PRIMARY_ISSUER",
        "APPROVED_OFFICIAL",
        "USER_SUPPLIED_OFFICIAL",
    }
    has_primary = any(item.authority in primary_authorities for item in supporting)
    has_support = bool(supporting)
    has_contradiction = bool(claim.contradicting_evidence_ids)
    band = (
        "HIGH"
        if has_primary and has_support and not has_contradiction
        else "MEDIUM"
        if has_support and not has_contradiction
        else "LOW"
    )
    factors: list[str] = []
    if has_primary:
        factors.append("Primary issuer evidence")
    if has_support:
        factors.append("Exact passage citation")
    if has_contradiction:
        factors.append("Contradicting evidence present")
    if not has_support:
        factors.append("No supporting evidence")
    return ClaimSupportAssessment(
        claim_id=claim.claim_id,
        band=band,
        supporting_evidence_ids=claim.supporting_evidence_ids,
        contradicting_evidence_ids=claim.contradicting_evidence_ids,
        factors=factors,
    )


def requires_abstention(assessment: ConfidenceAssessment) -> bool:
    """LOW means the candidate is retained for audit, not published as an explanation."""

    return assessment.band == "LOW"
