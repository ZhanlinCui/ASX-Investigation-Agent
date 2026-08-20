from __future__ import annotations

import pytest

from asx_investigator.confidence.calibration import (
    CalibrationRecord,
    attach_reviewed_calibration_metadata,
    build_calibration_artifact,
    review_calibration_artifact,
)
from asx_investigator.confidence.scoring import (
    ACTIVE_CONFIDENCE_RULE_VERSION,
    ConfidenceFeatures,
    score_confidence,
)
from asx_investigator.evaluation.gold import grade_external_holdout_records
from asx_investigator.evaluation.grading import evaluate_release_gates
from asx_investigator.evaluation.models import ReleaseGateReport
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway


def release_record(
    case_id: str,
    *,
    band: str = "MEDIUM",
    correct: bool = True,
    material_error: bool = False,
    checks: dict[str, bool] | None = None,
) -> CalibrationRecord:
    return CalibrationRecord(
        case_id=case_id,
        confidence_band=band,
        correct=correct,
        material_error=material_error,
        checks=checks or {},
    )


def test_high_band_material_error_blocks_release() -> None:
    gate = evaluate_release_gates(
        [release_record("case-1", band="HIGH", correct=False, material_error=True)]
    )

    assert gate.status == "FAIL"
    assert gate.raw_counts["wrong_high"] == {"passed": 0, "failed": 1}
    assert gate.denominators["wrong_high"] == 1


def test_missing_external_corpus_is_not_run() -> None:
    gate = evaluate_release_gates([], external_corpus_executed=False)

    assert gate.status == "NOT_RUN"
    assert gate.raw_counts == {}


def test_zero_eligible_behavioral_gate_does_not_pass_release() -> None:
    gate = evaluate_release_gates(
        [
            release_record(
                "case-1",
                checks={
                    "lookahead": True,
                    "session": True,
                    "citation": True,
                    "provider_semantics": True,
                    "reproducibility": True,
                    "confidence_caps": True,
                },
            )
        ]
    )

    assert gate.status == "FAIL"
    assert gate.denominators["top_1"] == 0
    assert "top_1 has no eligible cases" in gate.failures


def test_release_uses_actual_behavioral_denominators_and_thresholds() -> None:
    complete_checks = {
        "lookahead": True,
        "session": True,
        "citation": True,
        "provider_semantics": True,
        "reproducibility": True,
        "confidence_caps": True,
        "top_1": True,
        "top_2": True,
        "required_abstention": True,
        "false_abstention": True,
    }
    records = [
        release_record(f"case-{index}", checks=complete_checks)
        for index in range(1, 5)
    ]
    records.append(
        release_record(
            "case-5",
            checks={**complete_checks, "top_1": False, "top_2": False},
        )
    )

    gate = evaluate_release_gates(records)

    assert gate.status == "FAIL"
    assert gate.raw_counts["top_1"] == {"passed": 4, "failed": 1}
    assert gate.denominators["top_1"] == 5
    assert gate.proportions["top_1"] == 0.8
    assert gate.proportions["top_2"] == 0.8


def test_holdout_grading_cannot_change_the_active_confidence_rule() -> None:
    before = ACTIVE_CONFIDENCE_RULE_VERSION

    gate = grade_external_holdout_records(
        [
            CalibrationRecord(
                case_id="sealed-1",
                confidence_band="HIGH",
                correct=False,
                material_error=True,
                cohort="HOLDOUT",
            )
        ],
        external_corpus_executed=True,
    )

    assert gate.status == "FAIL"
    assert ACTIVE_CONFIDENCE_RULE_VERSION == before
    assert (
        score_confidence(ConfidenceFeatures(1, 1, 1, 1, 1, 1)).rule_version
        == ACTIVE_CONFIDENCE_RULE_VERSION
    )


def test_release_gate_report_rejects_mismatched_raw_count_denominators() -> None:
    with pytest.raises(ValueError, match="denominator"):
        ReleaseGateReport(
            status="FAIL",
            raw_counts={"top_1": {"passed": 3, "failed": 1}},
            denominators={"top_1": 3},
            proportions={"top_1": 1.0},
        )


async def test_only_a_matching_reviewed_artifact_can_attach_to_a_report() -> None:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )
    artifact = build_calibration_artifact(
        records=[
            CalibrationRecord(
                case_id=f"case-{index}",
                confidence_band=report.confidence.band,
                correct=True,
            )
            for index in range(5)
        ],
        corpus_version="gold-dev-v1",
        confidence_rule_version=report.confidence.rule_version,
    )
    reviewed = review_calibration_artifact(
        artifact,
        reviewer="evaluation-reviewer",
        reviewed_at=report.evidence[0].retrieved_at,
        creation_commit="abcdef1",
    )

    attached = attach_reviewed_calibration_metadata(report, reviewed)

    assert report.calibration_metadata.status == "NOT_RUN"
    assert attached.calibration_metadata.artifact_hash == artifact.artifact_hash
    assert attached.confidence.calibration_status == "MEASURED"
