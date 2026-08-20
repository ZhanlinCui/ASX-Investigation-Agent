from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from asx_investigator.domain.models import (
    Claim,
    ClaimSupportAssessment,
    ConfidenceAssessment,
    EvidenceItem,
)

ACTIVE_CONFIDENCE_RULE_VERSION = "confidence-v1"

# These are ordinal score bounds, never empirical probabilities.  Keeping the
# conditions and maxima in this module gives production scoring and release
# evaluation one source of truth.
CONFIDENCE_CAP_MAXIMA: Final[dict[str, float]] = {
    "NO_PRIMARY_EVIDENCE": 0.70,
    "DISCLOSURE_COVERAGE_PARTIAL": 0.65,
    "MATERIAL_CONFLICT": 0.60,
    "TIMING_UNRESOLVED": 0.60,
    "INTRADAY_DATA_MISSING": 0.65,
}


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


def required_confidence_caps(features: ConfidenceFeatures) -> list[str]:
    """Return the complete, deterministic cap set for observable features."""

    caps: list[str] = []
    if not features.has_primary_evidence:
        caps.append("NO_PRIMARY_EVIDENCE")
    if not features.disclosure_coverage_complete:
        caps.append("DISCLOSURE_COVERAGE_PARTIAL")
    if features.has_material_conflict:
        caps.append("MATERIAL_CONFLICT")
    if not features.timing_resolved:
        caps.append("TIMING_UNRESOLVED")
    if features.needs_intraday_data and not features.has_intraday_data:
        caps.append("INTRADAY_DATA_MISSING")
    return caps


def confidence_cap_maximum(caps: list[str]) -> float:
    """Return the strictest cap maximum and reject undeclared policy names."""

    unknown = sorted(set(caps) - set(CONFIDENCE_CAP_MAXIMA))
    if unknown:
        raise ValueError(f"Unknown confidence caps: {unknown}")
    return min((CONFIDENCE_CAP_MAXIMA[cap] for cap in caps), default=1.0)


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
    caps = required_confidence_caps(features)
    score = min(score, confidence_cap_maximum(caps))
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
