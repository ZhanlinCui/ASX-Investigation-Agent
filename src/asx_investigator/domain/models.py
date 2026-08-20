from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ClaimType(StrEnum):
    CAUSE = "CAUSE"
    CONTRIBUTOR = "CONTRIBUTOR"
    CONTEXT = "CONTEXT"
    MECHANICAL = "MECHANICAL"
    FACT = "FACT"
    UNRESOLVED = "UNRESOLVED"


class EvidenceRole(StrEnum):
    CAUSAL_INPUT = "CAUSAL_INPUT"
    CONTEMPORANEOUS_REACTION = "CONTEMPORANEOUS_REACTION"
    RETROSPECTIVE_CONTEXT = "RETROSPECTIVE_CONTEXT"
    EXCLUDED = "EXCLUDED"


class InvestigationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    FAILED_RECOVERABLE = "FAILED_RECOVERABLE"


class InvestigationOutcome(StrEnum):
    EXPLAINED = "EXPLAINED"
    NO_IDENTIFIABLE_CATALYST = "NO_IDENTIFIABLE_CATALYST"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INCOMPLETE_DATA = "INCOMPLETE_DATA"


class HypothesisStatus(StrEnum):
    LEADING = "LEADING"
    ALTERNATIVE = "ALTERNATIVE"
    MECHANICAL = "MECHANICAL"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ValidationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class InstrumentIdentity(BaseModel):
    asx_code: str
    company_name: str
    exchange: str = "ASX"
    currency: str = "AUD"
    sector: str | None = None


class TradingSession(BaseModel):
    trade_date: date
    timezone: str = "Australia/Sydney"
    timezone_label: str
    is_trading_day: bool
    market_open: datetime | None = None
    market_close: datetime | None = None
    previous_session: date | None = None
    next_session: date | None = None


class EventTiming(BaseModel):
    published_at: datetime
    session_relationship: str
    eligible_same_day_cause: bool
    eligible_next_day_cause: bool


class MarketMove(BaseModel):
    close_return_pct: float
    open_gap_pct: float
    open_to_close_pct: float
    turnover_aud: float
    volume_zscore: float | None
    return_zscore: float | None
    market_relative_return_pct: float | None
    is_unusual: bool
    resolution: str = "EOD"


class EvidenceItem(BaseModel):
    evidence_id: str
    source_name: str
    source_url: str
    published_at: datetime
    retrieved_at: datetime
    role: EvidenceRole
    authority: str
    title: str
    passage: str
    content_hash: str
    page: int | None = None
    locator: str | None = None
    supports_claim_ids: list[str] = Field(default_factory=list)
    contradicts_claim_ids: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    claim_id: str
    claim_type: ClaimType
    text: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None


class ConfidenceAssessment(BaseModel):
    score: float
    band: str
    calibration_status: str = "UNCALIBRATED"
    score_interpretation: str = "INTERNAL_ORDINAL_NOT_PROBABILITY"
    rule_version: str = "confidence-v1"
    selected_hypothesis_id: str | None = None
    positive_factors: list[str] = Field(default_factory=list)
    negative_factors: list[str] = Field(default_factory=list)
    applied_caps: list[str] = Field(default_factory=list)


class ClaimSupportAssessment(BaseModel):
    claim_id: str
    band: str
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    factors: list[str] = Field(default_factory=list)


class PrimaryAssessment(BaseModel):
    primary_claim_id: str | None = None
    summary: str


class Hypothesis(BaseModel):
    hypothesis_id: str
    rank: int = Field(ge=1, le=5)
    status: HypothesisStatus
    driver_label: str = "UNCLASSIFIED"
    statement: str
    expected_signature: str | None = None
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    validation_ids: list[str] = Field(default_factory=list)


class ValidationResult(BaseModel):
    validation_id: str
    kind: str
    status: ValidationStatus
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


class CoverageGap(BaseModel):
    gap_id: str
    capability: str
    provider: str
    reason: str
    impact: str
    retryable: bool = False


class SourceConflict(BaseModel):
    conflict_id: str
    field: str
    primary_source: str
    primary_value: str
    secondary_source: str
    secondary_value: str
    resolution: str
    material: bool = True


class CompletenessAssessment(BaseModel):
    score: float = Field(ge=0, le=1)
    status: str
    required_capabilities: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)


class TraceReference(BaseModel):
    event_count: int = Field(ge=0)
    last_sequence: int = Field(ge=0)


class InvestigationReport(BaseModel):
    case_id: str
    run_id: str
    status: InvestigationStatus
    outcome: InvestigationOutcome = InvestigationOutcome.INSUFFICIENT_EVIDENCE
    ticker: str
    trade_date: date
    timezone_label: str
    instrument: InstrumentIdentity
    market_move: MarketMove | None = None
    assessment: PrimaryAssessment
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: ConfidenceAssessment
    claim_support: list[ClaimSupportAssessment] = Field(default_factory=list)
    coverage_status: str
    completeness: CompletenessAssessment = Field(
        default_factory=lambda: CompletenessAssessment(score=0, status="UNKNOWN")
    )
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    validation_results: list[ValidationResult] = Field(default_factory=list)
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)
    conflicts: list[SourceConflict] = Field(default_factory=list)
    source_policy_version: str = "phase2-v1"
    model_configuration: dict[str, str] = Field(default_factory=dict)
    trace_reference: TraceReference | None = None
    parent_case_id: str | None = None
    case_version: int = Field(default=1, ge=1)
    trace: list[dict[str, str]] = Field(default_factory=list)
