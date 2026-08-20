import pytest

from asx_investigator.confidence.scoring import (
    ConfidenceFeatures,
    confidence_cap_maximum,
    required_confidence_caps,
    requires_abstention,
    score_confidence,
)


def test_missing_primary_evidence_caps_provisional_confidence() -> None:
    assessment = score_confidence(
        ConfidenceFeatures(
            source_authority=1.0,
            temporal_eligibility=1.0,
            market_signature_fit=1.0,
            quantitative_consistency=1.0,
            independent_corroboration=1.0,
            coverage_completeness=1.0,
            has_primary_evidence=False,
        )
    )

    assert assessment.score == 0.7
    assert "NO_PRIMARY_EVIDENCE" in assessment.applied_caps
    assert assessment.calibration_status == "UNCALIBRATED"
    assert assessment.score_interpretation == "INTERNAL_ORDINAL_NOT_PROBABILITY"


def test_material_conflict_and_unresolved_timing_apply_direct_caps() -> None:
    assessment = score_confidence(
        ConfidenceFeatures(
            source_authority=1,
            temporal_eligibility=1,
            market_signature_fit=1,
            quantitative_consistency=1,
            independent_corroboration=1,
            coverage_completeness=1,
            has_material_conflict=True,
            timing_resolved=False,
        )
    )

    assert assessment.band == "MEDIUM"
    assert "MATERIAL_CONFLICT" in assessment.applied_caps
    assert "TIMING_UNRESOLVED" in assessment.applied_caps


def test_stronger_contradiction_never_increases_confidence_band_score() -> None:
    base = ConfidenceFeatures(
        source_authority=1,
        temporal_eligibility=1,
        market_signature_fit=1,
        quantitative_consistency=1,
        independent_corroboration=1,
        coverage_completeness=1,
    )
    contradicted = ConfidenceFeatures(**{**base.__dict__, "contradiction_strength": 0.8})

    assert score_confidence(contradicted).score < score_confidence(base).score


@pytest.mark.parametrize(
    ("updates", "cap"),
    [
        ({"disclosure_coverage_complete": False}, "DISCLOSURE_COVERAGE_PARTIAL"),
        ({"has_material_conflict": True}, "MATERIAL_CONFLICT"),
        ({"timing_resolved": False}, "TIMING_UNRESOLVED"),
        (
            {"needs_intraday_data": True, "has_intraday_data": False},
            "INTRADAY_DATA_MISSING",
        ),
    ],
)
def test_each_confidence_cap_is_directly_exercised(
    updates: dict[str, bool], cap: str
) -> None:
    values = {
        "source_authority": 1,
        "temporal_eligibility": 1,
        "market_signature_fit": 1,
        "quantitative_consistency": 1,
        "independent_corroboration": 1,
        "coverage_completeness": 1,
        **updates,
    }

    assessment = score_confidence(ConfidenceFeatures(**values))

    assert cap in assessment.applied_caps
    assert assessment.band != "HIGH"


@pytest.mark.parametrize(
    ("updates", "expected_cap"),
    [
        ({"has_primary_evidence": False}, "NO_PRIMARY_EVIDENCE"),
        ({"disclosure_coverage_complete": False}, "DISCLOSURE_COVERAGE_PARTIAL"),
        ({"has_material_conflict": True}, "MATERIAL_CONFLICT"),
        ({"timing_resolved": False}, "TIMING_UNRESOLVED"),
        (
            {"needs_intraday_data": True, "has_intraday_data": False},
            "INTRADAY_DATA_MISSING",
        ),
    ],
)
def test_scoring_uses_the_shared_cap_rules_and_maxima(
    updates: dict[str, bool], expected_cap: str
) -> None:
    features = ConfidenceFeatures(
        source_authority=1,
        temporal_eligibility=1,
        market_signature_fit=1,
        quantitative_consistency=1,
        independent_corroboration=1,
        coverage_completeness=1,
        **updates,
    )

    required = required_confidence_caps(features)
    assessment = score_confidence(features)

    assert required == [expected_cap]
    assert assessment.applied_caps == required
    assert assessment.score <= confidence_cap_maximum(required)


def test_low_band_requires_abstention_but_medium_does_not() -> None:
    low = score_confidence(ConfidenceFeatures(0, 0, 0, 0, 0, 0))
    medium = score_confidence(ConfidenceFeatures(1, 1, 0.5, 0, 0, 0))

    assert requires_abstention(low) is True
    assert requires_abstention(medium) is False
