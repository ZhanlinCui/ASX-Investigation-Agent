"""Offline, ordinal calibration artifacts for reviewed confidence releases.

This module deliberately does not tune confidence scores. It aggregates
development-evaluation outcomes into immutable count-based artifacts. A
separate, explicit review step is required before metadata can appear in a
report or be admitted to shared product memory.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from asx_investigator.domain.models import CalibrationMetadata

if TYPE_CHECKING:
    from asx_investigator.domain.models import InvestigationReport
    from asx_investigator.evaluation.models import CaseEvaluation


CONFIDENCE_BANDS = ("LOW", "MEDIUM", "HIGH")
CALIBRATION_ARTIFACT_VERSION = "confidence-calibration-v1"
MINIMUM_BAND_SAMPLE = 5
RELEASE_CHECK_NAMES = {
    "lookahead",
    "session",
    "citation",
    "provider_semantics",
    "top_1",
    "top_2",
    "required_abstention",
    "false_abstention",
    "reproducibility",
    "confidence_caps",
}


class CalibrationRecord(BaseModel):
    """One explicitly validated evaluation outcome.

    The record is evaluation data, not product memory. Holdout records can be
    graded for release, but this class prevents them from becoming a calibration
    artifact. Outcome flags are mutually exclusive so the artifact's raw
    denominator is never inflated by double counting.
    """

    model_config = ConfigDict(frozen=True)

    case_id: str = Field(min_length=1, max_length=160)
    confidence_band: Literal["LOW", "MEDIUM", "HIGH"]
    correct: bool
    acceptable_alternative: bool = False
    abstained: bool = False
    material_error: bool = False
    cohort: Literal["DEVELOPMENT", "HOLDOUT"] = "DEVELOPMENT"
    checks: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_outcome_and_checks(self) -> CalibrationRecord:
        outcomes = (
            self.correct,
            self.acceptable_alternative,
            self.abstained,
            self.material_error,
        )
        if sum(bool(value) for value in outcomes) > 1:
            raise ValueError("Calibration outcome flags must be mutually exclusive")
        unknown = set(self.checks) - RELEASE_CHECK_NAMES
        if unknown:
            raise ValueError(f"Unknown release checks: {sorted(unknown)}")
        return self


class CalibrationArtifact(BaseModel):
    """A content-addressed development-only calibration snapshot."""

    model_config = ConfigDict(frozen=True)

    artifact_version: Literal["confidence-calibration-v1"] = CALIBRATION_ARTIFACT_VERSION
    label: str = "Evidence-strength band calibration"
    corpus_version: str = Field(min_length=1, max_length=160)
    confidence_rule_version: str = Field(min_length=1, max_length=80)
    status: Literal["MEASURED", "INSUFFICIENT_SAMPLE", "NOT_RUN"]
    bands: dict[str, CalibrationBand]
    artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_artifact_hash(self) -> CalibrationArtifact:
        if set(self.bands) != set(CONFIDENCE_BANDS):
            raise ValueError("Calibration artifacts must include LOW, MEDIUM and HIGH bands")
        expected = _artifact_hash(
            artifact_version=self.artifact_version,
            label=self.label,
            corpus_version=self.corpus_version,
            confidence_rule_version=self.confidence_rule_version,
            status=self.status,
            bands=self.bands,
        )
        if self.artifact_hash != expected:
            raise ValueError("Calibration artifact hash does not match its immutable contents")
        return self


class CalibrationBand(BaseModel):
    """An immutable count-only view of one ordinal confidence band."""

    model_config = ConfigDict(frozen=True)

    eligible_cases: int = Field(ge=0)
    correct_cases: int = Field(ge=0)
    acceptable_alternative_cases: int = Field(ge=0)
    abstained_cases: int = Field(ge=0)
    material_errors: int = Field(ge=0)
    status: Literal["MEASURED", "INSUFFICIENT_SAMPLE"]
    observed_correct_proportion: float = Field(ge=0, le=1)
    observed_acceptable_alternative_proportion: float = Field(ge=0, le=1)
    observed_abstention_proportion: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_counts_and_proportions(self) -> CalibrationBand:
        outcomes = (
            self.correct_cases,
            self.acceptable_alternative_cases,
            self.abstained_cases,
            self.material_errors,
        )
        if any(value > self.eligible_cases for value in outcomes):
            raise ValueError("Calibration band counts cannot exceed eligible_cases")
        if sum(outcomes) > self.eligible_cases:
            raise ValueError("Calibration band outcomes cannot exceed eligible_cases")
        expected_status = (
            "MEASURED"
            if self.eligible_cases >= MINIMUM_BAND_SAMPLE
            else "INSUFFICIENT_SAMPLE"
        )
        if self.status != expected_status:
            raise ValueError("Calibration band status does not match its sample size")
        denominator = self.eligible_cases
        expected_proportions = (
            self.correct_cases / denominator if denominator else 0.0,
            self.acceptable_alternative_cases / denominator if denominator else 0.0,
            self.abstained_cases / denominator if denominator else 0.0,
        )
        observed_proportions = (
            self.observed_correct_proportion,
            self.observed_acceptable_alternative_proportion,
            self.observed_abstention_proportion,
        )
        if observed_proportions != expected_proportions:
            raise ValueError("Calibration band proportions must match its raw counts")
        return self

    @classmethod
    def from_counts(
        cls,
        *,
        eligible_cases: int,
        correct_cases: int,
        acceptable_alternative_cases: int,
        abstained_cases: int,
        material_errors: int,
    ) -> CalibrationBand:
        denominator = eligible_cases
        return cls(
            eligible_cases=eligible_cases,
            correct_cases=correct_cases,
            acceptable_alternative_cases=acceptable_alternative_cases,
            abstained_cases=abstained_cases,
            material_errors=material_errors,
            status=(
                "MEASURED"
                if denominator >= MINIMUM_BAND_SAMPLE
                else "INSUFFICIENT_SAMPLE"
            ),
            observed_correct_proportion=correct_cases / denominator if denominator else 0.0,
            observed_acceptable_alternative_proportion=(
                acceptable_alternative_cases / denominator if denominator else 0.0
            ),
            observed_abstention_proportion=abstained_cases / denominator if denominator else 0.0,
        )


class ReviewedCalibrationArtifact(BaseModel):
    """A calibration artifact explicitly approved for report metadata.

    Review is intentionally a pure value transformation. It cannot write an
    active rule, tune a score, or place a result in shared memory.
    """

    model_config = ConfigDict(frozen=True)

    artifact: CalibrationArtifact
    reviewer: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    creation_commit: str = Field(pattern=r"^[0-9a-f]{7,64}$")

    @model_validator(mode="after")
    def validate_review_timestamp(self) -> ReviewedCalibrationArtifact:
        if self.reviewed_at.tzinfo is None:
            raise ValueError("reviewed_at must include a timezone")
        return self


def build_calibration_artifact(
    records: list[CalibrationRecord],
    *,
    corpus_version: str,
    confidence_rule_version: str,
) -> CalibrationArtifact:
    """Build a deterministic artifact from development records only."""

    if any(record.cohort != "DEVELOPMENT" for record in records):
        raise ValueError("Calibration artifacts can only use development records")
    bands: dict[str, CalibrationBand] = {}
    for band in CONFIDENCE_BANDS:
        grouped = [record for record in records if record.confidence_band == band]
        eligible_cases = len(grouped)
        bands[band] = CalibrationBand.from_counts(
            eligible_cases=eligible_cases,
            correct_cases=sum(record.correct for record in grouped),
            acceptable_alternative_cases=sum(
                record.acceptable_alternative for record in grouped
            ),
            abstained_cases=sum(record.abstained for record in grouped),
            material_errors=sum(record.material_error for record in grouped),
        )
    status: Literal["MEASURED", "INSUFFICIENT_SAMPLE", "NOT_RUN"]
    if not records:
        status = "NOT_RUN"
    elif any(item.status == "MEASURED" for item in bands.values()):
        status = "MEASURED"
    else:
        status = "INSUFFICIENT_SAMPLE"
    artifact_hash = _artifact_hash(
        artifact_version=CALIBRATION_ARTIFACT_VERSION,
        label="Evidence-strength band calibration",
        corpus_version=corpus_version,
        confidence_rule_version=confidence_rule_version,
        status=status,
        bands=bands,
    )
    return CalibrationArtifact(
        corpus_version=corpus_version,
        confidence_rule_version=confidence_rule_version,
        status=status,
        bands=bands,
        artifact_hash=artifact_hash,
    )


def review_calibration_artifact(
    artifact: CalibrationArtifact,
    *,
    reviewer: str,
    reviewed_at: datetime,
    creation_commit: str,
) -> ReviewedCalibrationArtifact:
    """Return a reviewed value without changing any active confidence rule."""

    return ReviewedCalibrationArtifact(
        artifact=artifact,
        reviewer=reviewer,
        reviewed_at=reviewed_at,
        creation_commit=creation_commit,
    )


def calibration_metadata_from_reviewed_artifact(
    artifact: ReviewedCalibrationArtifact,
) -> CalibrationMetadata:
    """Derive the report-safe metadata view from an explicit review only."""

    if not isinstance(artifact, ReviewedCalibrationArtifact):
        raise ValueError("Calibration metadata requires a reviewed calibration artifact")
    return CalibrationMetadata(
        label=artifact.artifact.label,
        status=artifact.artifact.status,
        corpus_version=artifact.artifact.corpus_version,
        confidence_rule_version=artifact.artifact.confidence_rule_version,
        created_at=artifact.reviewed_at,
        creation_commit=artifact.creation_commit,
        artifact_hash=artifact.artifact.artifact_hash,
        reviewed_by=artifact.reviewer,
        reviewed_at=artifact.reviewed_at,
        bands={
            band: artifact.artifact.bands[band].model_dump()
            for band in CONFIDENCE_BANDS
        },
    )


def attach_reviewed_calibration_metadata(
    report: InvestigationReport,
    artifact: ReviewedCalibrationArtifact,
) -> InvestigationReport:
    """Return a report copy with metadata from its matching reviewed artifact.

    This is intentionally not called by scoring or evaluation. Selecting a
    reviewed artifact remains an explicit versioned-release action outside an
    individual investigation or holdout execution.
    """

    if not isinstance(artifact, ReviewedCalibrationArtifact):
        raise ValueError("Report calibration metadata requires a reviewed artifact")
    if report.confidence.rule_version != artifact.artifact.confidence_rule_version:
        raise ValueError("Reviewed artifact rule version does not match the report")
    band_status = artifact.artifact.bands[report.confidence.band].status
    confidence = report.confidence.model_copy(update={"calibration_status": band_status})
    return report.model_copy(
        update={
            "confidence": confidence,
            "calibration_metadata": calibration_metadata_from_reviewed_artifact(artifact),
        }
    )


def calibration_record_from_evaluation(
    report: InvestigationReport,
    evaluation: CaseEvaluation,
    *,
    cohort: Literal["DEVELOPMENT", "HOLDOUT"],
    material_error: bool,
) -> CalibrationRecord:
    """Translate a completed report and deterministic grader output to one record.

    ``material_error`` remains an external adjudication input. The product
    never lets an LLM or a holdout execution decide that label on its own.
    """

    check_by_name = {check.name: check.passed for check in evaluation.checks}
    report_band = report.confidence.band
    if report_band not in CONFIDENCE_BANDS:
        raise ValueError("Report confidence band is not recognized")
    if evaluation.confidence_band is not None and evaluation.confidence_band != report_band:
        raise ValueError("Evaluation confidence band must match the report confidence band")
    abstained = str(report.outcome) != "EXPLAINED"
    top_one = check_by_name.get("top_1_attribution", False)
    top_two = check_by_name.get("top_2_attribution", False)
    return CalibrationRecord(
        case_id=evaluation.case_id,
        confidence_band=report_band,
        correct=top_one and not abstained and not material_error,
        acceptable_alternative=top_two and not top_one and not abstained and not material_error,
        abstained=abstained and not material_error,
        material_error=material_error,
        cohort=cohort,
        checks=_release_checks_from_grader(check_by_name, evaluation.abstention_policy),
    )


def _release_checks_from_grader(
    checks: dict[str, bool], abstention_policy: str | None
) -> dict[str, bool]:
    """Map stable deterministic grader names to the release-gate contract."""

    mapped = {
        "lookahead": checks.get("temporal_integrity"),
        "session": checks.get("session_integrity"),
        "citation": _all_present(
            checks,
            "grounding",
            "assertion_integrity",
            "claim_compilation",
        ),
        "provider_semantics": checks.get("provider_failure_semantics"),
        "top_1": checks.get("top_1_attribution"),
        "top_2": checks.get("top_2_attribution"),
        "reproducibility": checks.get("ledger_reproducibility"),
        "confidence_caps": checks.get("confidence_caps"),
    }
    if abstention_policy == "REQUIRED":
        mapped["required_abstention"] = checks.get("abstention")
    elif abstention_policy == "FORBIDDEN":
        mapped["false_abstention"] = checks.get("abstention")
    return {name: value for name, value in mapped.items() if value is not None}


def _all_present(checks: dict[str, bool], *names: str) -> bool | None:
    values = [checks.get(name) for name in names]
    return None if any(value is None for value in values) else all(values)


def _artifact_hash(
    *,
    artifact_version: str,
    label: str,
    corpus_version: str,
    confidence_rule_version: str,
    status: str,
    bands: dict[str, CalibrationBand],
) -> str:
    payload = {
        "artifact_version": artifact_version,
        "label": label,
        "corpus_version": corpus_version,
        "confidence_rule_version": confidence_rule_version,
        "status": status,
        "bands": {name: bands[name].model_dump(mode="json") for name in sorted(bands)},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
