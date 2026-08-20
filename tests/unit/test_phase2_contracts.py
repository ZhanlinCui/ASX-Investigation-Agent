from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from asx_investigator.domain.models import (
    CompletenessAssessment,
    CoverageGap,
    Hypothesis,
    HypothesisStatus,
    InstrumentIdentity,
    InvestigationOutcome,
    InvestigationReport,
    InvestigationStatus,
    PrimaryAssessment,
    SourceConflict,
    ValidationResult,
    ValidationStatus,
)
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus


def test_report_separates_lifecycle_outcome_and_completeness() -> None:
    report = InvestigationReport(
        case_id="case-1",
        run_id="run-1",
        status=InvestigationStatus.COMPLETED,
        outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE,
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        timezone_label="AEST",
        instrument=InstrumentIdentity(asx_code="BHP", company_name="BHP Group Limited"),
        assessment=PrimaryAssessment(summary="No eligible primary evidence was found."),
        confidence={"score": 0.35, "band": "LOW"},
        completeness=CompletenessAssessment(
            score=0.5,
            status="PARTIAL",
            required_capabilities=["market_data", "issuer_disclosures"],
            missing_capabilities=["issuer_disclosures"],
        ),
        coverage_status="PARTIAL",
        hypotheses=[
            Hypothesis(
                hypothesis_id="H1",
                rank=1,
                status=HypothesisStatus.INSUFFICIENT_EVIDENCE,
                statement="A company-specific catalyst is possible but unsupported.",
            )
        ],
        coverage_gaps=[
            CoverageGap(
                gap_id="G1",
                capability="issuer_disclosures",
                provider="issuer_ir",
                reason="No complete archive was available.",
                impact="Causal confidence is capped.",
            )
        ],
    )

    payload = report.model_dump(mode="json")

    assert payload["status"] == "COMPLETED"
    assert payload["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert payload["completeness"]["status"] == "PARTIAL"
    assert payload["coverage_gaps"][0]["gap_id"] == "G1"


def test_report_preserves_conflicts_and_validation_results() -> None:
    conflict = SourceConflict(
        conflict_id="CF1",
        field="close",
        primary_source="EODHD",
        primary_value="11.00",
        secondary_source="Marketstack",
        secondary_value="10.90",
        resolution="EODHD selected by field policy; confidence cap applied.",
        material=True,
    )
    validation = ValidationResult(
        validation_id="V1",
        kind="TEMPORAL",
        status=ValidationStatus.PASS,
        summary="Evidence was published before the ASX session opened.",
        evidence_ids=["E1"],
    )

    assert conflict.material is True
    assert validation.status == "PASS"


def test_provider_outcome_distinguishes_empty_from_failure() -> None:
    now = datetime.now(UTC)
    empty = ProviderOutcome[list[int]](
        status=ProviderStatus.EMPTY,
        provider="example",
        retrieved_at=now,
        coverage="COMPLETE",
        data=[],
    )
    failure = ProviderOutcome[list[int]](
        status=ProviderStatus.RETRYABLE_FAILURE,
        provider="example",
        retrieved_at=now,
        coverage="NONE",
        error_code="TIMEOUT",
    )

    assert empty.succeeded is True
    assert failure.succeeded is False
    assert failure.error_code == "TIMEOUT"


def test_provider_success_requires_data() -> None:
    with pytest.raises(ValidationError):
        ProviderOutcome[list[int]](
            status=ProviderStatus.SUCCESS,
            provider="example",
            retrieved_at=datetime.now(UTC),
            coverage="COMPLETE",
        )
