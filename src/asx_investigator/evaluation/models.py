from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


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


class EvaluationReport(BaseModel):
    suite_version: str
    fixture_kind: str
    status: Literal["PASSED", "FAILED", "NOT_RUN"]
    raw_counts: dict[str, int]
    proportions: dict[str, float]
    cases: list[CaseEvaluation] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
