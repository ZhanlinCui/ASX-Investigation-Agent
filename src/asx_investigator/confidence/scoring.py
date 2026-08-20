from __future__ import annotations

from dataclasses import dataclass

from asx_investigator.domain.models import ConfidenceAssessment


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
    if features.needs_intraday_data and not features.has_intraday_data:
        score = min(score, 0.65)
        caps.append("INTRADAY_DATA_MISSING")
    score = round(score, 2)
    band = "HIGH" if score >= 0.75 else "MEDIUM" if score >= 0.45 else "LOW"
    return ConfidenceAssessment(
        score=score,
        band=band,
        positive_factors=["Primary evidence present"] if features.has_primary_evidence else [],
        negative_factors=caps.copy(),
        applied_caps=caps,
    )

