from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

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
from asx_investigator.domain.models import SourceConflict
from asx_investigator.evaluation.gold import grade_external_holdout_records
from asx_investigator.evaluation.grading import _confidence_caps, evaluate_release_gates
from asx_investigator.evaluation.models import ReleaseGateReport
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.live import DataProviderUnavailable
from asx_investigator.providers.recorded import RecordedToolGateway


class MissingMarketGateway(RecordedToolGateway):
    async def get_market_data(self, ticker, trade_date):
        raise DataProviderUnavailable("market data unavailable for calibration regression")


class PartialDisclosureGateway(RecordedToolGateway):
    async def disclosure_coverage_complete(self, ticker, trade_date):
        return False


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


_REQUIRED_SAFETY_CHECKS = (
    "lookahead",
    "session",
    "citation",
    "provider_semantics",
    "reproducibility",
    "confidence_caps",
)


_COMPLETE_RELEASE_CHECKS = {
    **{name: True for name in _REQUIRED_SAFETY_CHECKS},
    "top_1": True,
    "top_2": True,
}


@pytest.mark.parametrize("missing_check", _REQUIRED_SAFETY_CHECKS)
def test_each_unobserved_required_safety_check_blocks_a_nonempty_release(
    missing_check: str,
) -> None:
    checks = {key: value for key, value in _COMPLETE_RELEASE_CHECKS.items() if key != missing_check}

    gate = evaluate_release_gates(
        [release_record("case-1", band="HIGH", checks=checks)]
    )

    assert gate.status == "FAIL"
    assert gate.denominators[missing_check] == 0
    assert f"{missing_check} has no eligible observations" in gate.failures


def test_unobserved_high_confidence_safety_check_blocks_a_nonempty_release() -> None:
    gate = evaluate_release_gates(
        [release_record("case-1", band="MEDIUM", checks=_COMPLETE_RELEASE_CHECKS)]
    )

    assert gate.status == "FAIL"
    assert gate.denominators["wrong_high"] == 0
    assert "wrong_high has no eligible observations" in gate.failures


def test_release_blocks_when_required_abstention_has_no_eligible_case() -> None:
    gate = evaluate_release_gates(
        [release_record("case-1", band="HIGH", checks=_COMPLETE_RELEASE_CHECKS)]
    )

    assert gate.status == "FAIL"
    assert gate.denominators["required_abstention"] == 0
    assert gate.denominators["false_abstention"] == 0
    assert "required_abstention has no eligible cases" in gate.failures


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


def test_required_abstentions_do_not_dilute_answerable_attribution_failures() -> None:
    answerable_checks = {
        **_COMPLETE_RELEASE_CHECKS,
        "top_1": False,
        "top_2": False,
    }
    required_abstention_checks = {
        **_COMPLETE_RELEASE_CHECKS,
        "required_abstention": True,
    }
    records = [release_record("answerable-failure", band="HIGH", checks=answerable_checks)]
    records.extend(
        release_record(
            f"required-abstention-{index}",
            checks=required_abstention_checks,
        )
        for index in range(20)
    )

    gate = evaluate_release_gates(records)

    assert gate.status == "FAIL"
    assert gate.raw_counts["top_1"] == {"passed": 0, "failed": 1}
    assert gate.denominators["top_1"] == 1
    assert gate.raw_counts["top_2"] == {"passed": 0, "failed": 1}
    assert gate.denominators["top_2"] == 1
    assert gate.denominators["required_abstention"] == 20
    assert "top_1 is below the 75% threshold" in gate.failures


def test_release_requires_observed_required_abstention_behavior() -> None:
    records = [
        release_record(
            f"answerable-{index}",
            band="HIGH" if index == 0 else "MEDIUM",
            checks=_COMPLETE_RELEASE_CHECKS,
        )
        for index in range(24)
    ]

    gate = evaluate_release_gates(records)

    assert gate.status == "FAIL"
    assert gate.denominators["required_abstention"] == 0
    assert "required_abstention has no eligible cases" in gate.failures


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


async def test_confidence_cap_release_check_derives_requirements_from_report_state() -> None:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )
    elevated = report.confidence.model_copy(
        update={"score": 0.99, "band": "HIGH", "applied_caps": []}
    )
    in_session_evidence = report.evidence[0].model_copy(
        update={
            "published_at": datetime(
                2026, 8, 20, 11, tzinfo=ZoneInfo("Australia/Sydney")
            )
        }
    )
    candidates = [
        (
            "NO_PRIMARY_EVIDENCE",
            report.model_copy(
                update={
                    "evidence": [
                        report.evidence[0].model_copy(update={"authority": "DISCOVERY"})
                    ],
                    "confidence": elevated,
                }
            ),
        ),
        (
            "DISCLOSURE_COVERAGE_PARTIAL",
            report.model_copy(
                update={
                    "coverage_status": "PARTIAL_DISCLOSURE_COVERAGE",
                    "confidence": elevated,
                }
            ),
        ),
        (
            "MATERIAL_CONFLICT",
            report.model_copy(
                update={
                    "conflicts": [
                        SourceConflict(
                            conflict_id="CONFLICT-1",
                            field="close",
                            primary_source="EODHD",
                            primary_value="10.00",
                            secondary_source="Marketstack",
                            secondary_value="10.10",
                            resolution="Not averaged; primary retained.",
                            material=True,
                        )
                    ],
                    "confidence": elevated,
                }
            ),
        ),
        (
            "TIMING_UNRESOLVED",
            report.model_copy(
                update={"evidence": [in_session_evidence], "confidence": elevated}
            ),
        ),
        (
            "INTRADAY_DATA_MISSING",
            report.model_copy(
                update={"evidence": [in_session_evidence], "confidence": elevated}
            ),
        ),
    ]

    for expected_cap, candidate in candidates:
        passed, detail = _confidence_caps(candidate)

        assert passed is False
        assert expected_cap in detail


@pytest.mark.parametrize(
    ("trade_date", "gateway", "expected_coverage_status"),
    [
        ("2026-08-22", RecordedToolGateway.default(), "NOT_A_TRADING_DAY"),
        ("2026-08-20", MissingMarketGateway(), "INCOMPLETE_MARKET_DATA"),
    ],
)
async def test_confidence_cap_release_check_keeps_pre_evidence_failures_at_primary_cap_only(
    trade_date: str,
    gateway: RecordedToolGateway,
    expected_coverage_status: str,
) -> None:
    report = await InvestigationService(gateway).investigate(
        "BHP", trade_date, mode="RECORDED"
    )

    passed, detail = _confidence_caps(report)

    assert report.coverage_status == expected_coverage_status
    assert report.confidence.applied_caps == ["NO_PRIMARY_EVIDENCE"]
    assert passed is True
    assert "required_caps=['NO_PRIMARY_EVIDENCE']" in detail


async def test_confidence_cap_release_check_detects_missing_disclosure_cap_for_partial_evidence(
) -> None:
    report = await InvestigationService(PartialDisclosureGateway()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )
    without_disclosure_cap = report.model_copy(
        update={
            "confidence": report.confidence.model_copy(
                update={"applied_caps": ["NO_PRIMARY_EVIDENCE"]}
            )
        }
    )

    passed, detail = _confidence_caps(without_disclosure_cap)

    assert report.coverage_status == "PARTIAL_DISCLOSURE_COVERAGE"
    assert "DISCLOSURE_COVERAGE_PARTIAL" in report.confidence.applied_caps
    assert passed is False
    assert "DISCLOSURE_COVERAGE_PARTIAL" in detail
