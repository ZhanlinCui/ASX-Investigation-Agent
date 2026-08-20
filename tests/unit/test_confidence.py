from asx_investigator.confidence.scoring import ConfidenceFeatures, score_confidence


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
