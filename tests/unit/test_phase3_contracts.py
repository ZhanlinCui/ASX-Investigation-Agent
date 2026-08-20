from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from asx_investigator.domain.models import (
    BandCalibrationMetadata,
    CalibrationMetadata,
    CausalMechanism,
    EvidenceAssertion,
    EvidenceRole,
    InstrumentIdentity,
    InvestigationReport,
    InvestigationStatus,
    LedgerEntry,
    MechanismTest,
    PrimaryAssessment,
    ValidationStatus,
)


def test_assertion_requires_case_scoped_evidence_and_exact_span_hash() -> None:
    assertion = EvidenceAssertion(
        assertion_id="A1",
        evidence_id="E1",
        case_version_id="version-1",
        exact_text="BHP raised FY26 production guidance.",
        span_hash="a" * 64,
        artifact_hash="b" * 64,
        published_at=datetime(2026, 8, 20, 8, 30, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 20, 8, 31, tzinfo=UTC),
        source_authority="ISSUER_PRIMARY",
        locator="page=1;block=3",
        role=EvidenceRole.CAUSAL_INPUT,
        causal_eligible=True,
    )

    assert assertion.mechanism_hint == CausalMechanism.UNKNOWN
    assert assertion.locator == "page=1;block=3"


def test_assertion_rejects_non_sha256_span_hash() -> None:
    with pytest.raises(ValidationError, match="span_hash"):
        EvidenceAssertion(
            assertion_id="A1",
            evidence_id="E1",
            case_version_id="version-1",
            exact_text="BHP raised FY26 production guidance.",
            span_hash="bad",
            artifact_hash="b" * 64,
            published_at=datetime.now(UTC),
            retrieved_at=datetime.now(UTC),
            source_authority="ISSUER_PRIMARY",
            role=EvidenceRole.CAUSAL_INPUT,
            causal_eligible=True,
        )


def test_assertion_rejects_non_sha256_artifact_hash() -> None:
    with pytest.raises(ValidationError, match="artifact_hash"):
        EvidenceAssertion(
            assertion_id="A1",
            evidence_id="E1",
            case_version_id="version-1",
            exact_text="BHP raised FY26 production guidance.",
            span_hash="a" * 64,
            artifact_hash="not-a-sha256",
            published_at=datetime.now(UTC),
            retrieved_at=datetime.now(UTC),
            source_authority="ISSUER_PRIMARY",
            role=EvidenceRole.CAUSAL_INPUT,
            causal_eligible=True,
        )


def test_mechanism_test_and_ledger_capture_auditable_versions() -> None:
    observed_at = datetime(2026, 8, 20, 8, 45, tzinfo=UTC)
    mechanism_test = MechanismTest(
        test_id="MT-ISSUER-EVENT",
        mechanism=CausalMechanism.ISSUER_EVENT,
        status=ValidationStatus.PASS,
        summary="An eligible issuer disclosure contains the guidance update.",
        taxonomy_version="causal-mechanisms-v1",
        policy_version="source-policy-v3",
        created_at=observed_at,
        supporting_assertion_ids=["A1"],
    )
    ledger_entry = LedgerEntry(
        sequence=1,
        stage="test_mechanisms",
        status="COMPLETED",
        input_hashes=["a" * 64],
        output_hashes=["b" * 64],
        schema_version="ledger-v1",
        policy_version="source-policy-v3",
        model_configuration={"model": "gemini-3-flash-preview"},
        validation_status=ValidationStatus.PASS,
        validation_summary="Mechanism tests completed.",
        created_at=observed_at,
    )

    assert mechanism_test.taxonomy_version == "causal-mechanisms-v1"
    assert ledger_entry.validation_status == ValidationStatus.PASS


def test_calibration_metadata_computes_observed_proportions_and_rejects_bad_counts() -> None:
    with pytest.raises(ValidationError, match="correct_cases"):
        BandCalibrationMetadata(
            eligible_cases=1,
            correct_cases=2,
            acceptable_alternative_cases=0,
            abstained_cases=0,
            material_errors=0,
            status="MEASURED",
        )

    with pytest.raises(ValidationError, match="outcome counts"):
        BandCalibrationMetadata(
            eligible_cases=1,
            correct_cases=1,
            acceptable_alternative_cases=0,
            abstained_cases=0,
            material_errors=1,
            status="MEASURED",
        )

    with pytest.raises(ValidationError, match="zero eligible cases"):
        BandCalibrationMetadata(
            eligible_cases=0,
            correct_cases=0,
            acceptable_alternative_cases=0,
            abstained_cases=0,
            material_errors=0,
            status="NOT_RUN",
            observed_correct_proportion=0.1,
        )

    metadata = CalibrationMetadata(
        status="MEASURED",
        corpus_version="gold-dev-v1",
        confidence_rule_version="confidence-v2",
        created_at=datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
        creation_commit="abcdef1",
        bands={
            "HIGH": BandCalibrationMetadata(
                eligible_cases=10,
                correct_cases=7,
                acceptable_alternative_cases=1,
                abstained_cases=1,
                material_errors=1,
                status="MEASURED",
            )
        },
    )

    assert metadata.bands["HIGH"].observed_correct_proportion == 0.7
    assert metadata.bands["HIGH"].observed_abstention_proportion == 0.1


def test_phase2_report_payload_still_parses_with_phase3_defaults() -> None:
    phase2_payload = {
        "case_id": "case-1",
        "run_id": "run-1",
        "status": InvestigationStatus.COMPLETED,
        "ticker": "BHP",
        "trade_date": date(2026, 8, 20),
        "timezone_label": "AEST",
        "instrument": InstrumentIdentity(
            asx_code="BHP", company_name="BHP Group Limited"
        ),
        "assessment": PrimaryAssessment(summary="No eligible evidence was found."),
        "confidence": {"score": 0.35, "band": "LOW"},
        "coverage_status": "PARTIAL",
    }

    report = InvestigationReport.model_validate(phase2_payload)

    assert report.assertions == []
    assert report.mechanism_tests == []
    assert report.ledger == []
    assert report.calibration_metadata.status == "NOT_RUN"
