from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from asx_investigator.confidence.calibration import (
    CalibrationRecord,
    build_calibration_artifact,
    calibration_metadata_from_reviewed_artifact,
    review_calibration_artifact,
)


def calibration_record(
    band: str,
    *,
    correct: bool,
    material_error: bool = False,
    case_id: str = "case-1",
) -> CalibrationRecord:
    return CalibrationRecord(
        case_id=case_id,
        confidence_band=band,
        correct=correct,
        material_error=material_error,
    )


def test_calibration_artifact_marks_small_band_samples_insufficient() -> None:
    artifact = build_calibration_artifact(
        records=[
            calibration_record("HIGH", correct=True, case_id=f"case-{index}")
            for index in range(4)
        ],
        corpus_version="gold-dev-v1",
        confidence_rule_version="confidence-v2",
    )

    assert artifact.bands["HIGH"].status == "INSUFFICIENT_SAMPLE"
    assert artifact.bands["HIGH"].eligible_cases == 4
    assert artifact.bands["HIGH"].observed_correct_proportion == 1.0
    assert "probability" not in artifact.label.lower()


def test_calibration_artifact_rejects_holdout_records() -> None:
    with pytest.raises(ValueError, match="development"):
        build_calibration_artifact(
            records=[
                CalibrationRecord(
                    case_id="sealed-1",
                    confidence_band="HIGH",
                    correct=True,
                    cohort="HOLDOUT",
                )
            ],
            corpus_version="sealed-v1",
            confidence_rule_version="confidence-v2",
        )


def test_calibration_artifact_is_immutable_at_the_band_level() -> None:
    artifact = build_calibration_artifact(
        records=[
            calibration_record("MEDIUM", correct=True, case_id=f"case-{index}")
            for index in range(5)
        ],
        corpus_version="gold-dev-v1",
        confidence_rule_version="confidence-v2",
    )

    with pytest.raises(ValidationError, match="frozen"):
        artifact.bands["MEDIUM"].correct_cases = 0


def test_only_a_reviewed_artifact_can_become_report_metadata() -> None:
    artifact = build_calibration_artifact(
        records=[
            calibration_record("LOW", correct=True, case_id=f"case-{index}")
            for index in range(5)
        ],
        corpus_version="gold-dev-v1",
        confidence_rule_version="confidence-v2",
    )

    with pytest.raises(ValueError, match="reviewed"):
        calibration_metadata_from_reviewed_artifact(artifact)  # type: ignore[arg-type]

    reviewed = review_calibration_artifact(
        artifact,
        reviewer="evaluation-reviewer",
        reviewed_at=datetime(2026, 8, 21, tzinfo=UTC),
        creation_commit="abcdef1",
    )
    metadata = calibration_metadata_from_reviewed_artifact(reviewed)

    assert metadata.status == "MEASURED"
    assert metadata.confidence_rule_version == "confidence-v2"
    assert metadata.bands["LOW"].eligible_cases == 5
    assert metadata.artifact_hash == artifact.artifact_hash
    assert metadata.reviewed_by == "evaluation-reviewer"
