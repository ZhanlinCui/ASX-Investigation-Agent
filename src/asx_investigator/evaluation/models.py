from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from asx_investigator.domain.models import InvestigationReport


class EvalCaseManifest(BaseModel):
    manifest_version: str = "eval-case-v1"
    case_id: str
    category: str
    scenario: str
    ticker: str
    trade_date: date
    evidence_cutoff: datetime
    driver_labels: list[str]
    acceptable_alternatives: list[str]
    required_evidence_ids: list[str]
    future_evidence_blacklist: list[str]
    mechanical_flags: list[str]
    coverage_expectation: str
    abstention_policy: Literal["REQUIRED", "ALLOWED", "FORBIDDEN"]
    expected_outcome: str
    max_latency_ms: int = Field(default=30_000, gt=0)
    max_cost_aud: float = Field(default=1.0, ge=0)


class EvalSuiteManifest(BaseModel):
    suite_version: str
    fixture_kind: str
    cases: list[EvalCaseManifest]


class GraderCheck(BaseModel):
    name: str
    passed: bool
    detail: str
    hard_gate: bool = True


class CaseEvaluation(BaseModel):
    case_id: str
    passed: bool
    checks: list[GraderCheck]
    raw_counts: dict[str, int]
    latency_ms: int
    estimated_cost_aud: float
    confidence_band: Literal["LOW", "MEDIUM", "HIGH"] | None = None
    abstention_policy: Literal["REQUIRED", "ALLOWED", "FORBIDDEN"] | None = None


class EvaluationReport(BaseModel):
    suite_version: str
    fixture_kind: str
    status: Literal["PASSED", "FAILED", "NOT_RUN"]
    raw_counts: dict[str, int]
    proportions: dict[str, float]
    cases: list[CaseEvaluation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ReleaseGateReport(BaseModel):
    """A deterministic release decision with unambiguous denominators."""

    status: Literal["PASS", "FAIL", "NOT_RUN"]
    raw_counts: dict[str, dict[str, int]]
    denominators: dict[str, int]
    proportions: dict[str, float]
    failures: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_raw_counts(self) -> ReleaseGateReport:
        if self.status == "NOT_RUN":
            if self.raw_counts or self.denominators or self.proportions:
                raise ValueError("NOT_RUN release gates cannot contain evaluated counts")
            return self
        if set(self.raw_counts) != set(self.denominators) or set(self.raw_counts) != set(
            self.proportions
        ):
            raise ValueError("release-gate counts, denominators and proportions must align")
        for name, count in self.raw_counts.items():
            if set(count) != {"passed", "failed"}:
                raise ValueError("release-gate raw counts require passed and failed values")
            if count["passed"] < 0 or count["failed"] < 0:
                raise ValueError("release-gate raw counts cannot be negative")
            if self.denominators[name] != count["passed"] + count["failed"]:
                raise ValueError("release-gate denominator must match its raw counts")
            expected = count["passed"] / self.denominators[name] if self.denominators[name] else 0.0
            if self.proportions[name] != expected:
                raise ValueError("release-gate proportion must match its raw counts")
        return self


class GoldCaseManifest(BaseModel):
    case_id: str
    ticker: str
    trade_date: date
    timezone: str
    evidence_cutoff: datetime
    artifact_ids: list[str] = Field(min_length=1)
    eligible_evidence_ids: list[str] = Field(default_factory=list)
    future_evidence_ids: list[str] = Field(default_factory=list)
    driver_labels: list[str] = Field(min_length=1)
    acceptable_alternatives: list[str] = Field(default_factory=list)
    mechanical_expectation: str
    coverage_expectation: str
    citation_requirements: list[str] = Field(default_factory=list)
    abstention_allowed: bool
    expected_outcome: Literal[
        "EXPLAINED",
        "NO_IDENTIFIABLE_CATALYST",
        "INSUFFICIENT_EVIDENCE",
        "INCOMPLETE_DATA",
    ] = "EXPLAINED"


class GoldCorpusLoadResult(BaseModel):
    corpus: Literal["development", "holdout"]
    status: Literal["PASS", "FAIL", "NOT_RUN"]
    cases: list[GoldCaseManifest] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    reason: str | None = None


class GoldCaseFailure(BaseModel):
    case_id: str
    failed_checks: list[str]


class GoldReleaseReport(BaseModel):
    status: Literal["PASS", "FAIL", "NOT_RUN"]
    raw_counts: dict[str, dict[str, int]]
    proportions: dict[str, float]
    case_failures: list[GoldCaseFailure] = Field(default_factory=list)


class GoldExecutionCase(BaseModel):
    """One production-path run of a frozen bundle.

    `evaluation` is deliberately absent for a sealed holdout run. The report is
    still available for an external grader to join with labels outside product
    runtime.
    """

    case_id: str
    report: InvestigationReport
    evaluation: CaseEvaluation | None = None


class GoldExecutionReport(BaseModel):
    corpus: Literal["development", "holdout"]
    corpus_version: str | None = None
    status: Literal["PASS", "FAIL", "NOT_RUN"]
    cases: list[GoldExecutionCase] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    reason: str | None = None
