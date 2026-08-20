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
    positive_factors: list[str] = Field(default_factory=list)
    negative_factors: list[str] = Field(default_factory=list)
    applied_caps: list[str] = Field(default_factory=list)


class PrimaryAssessment(BaseModel):
    primary_claim_id: str | None = None
    summary: str


class InvestigationReport(BaseModel):
    case_id: str
    run_id: str
    status: InvestigationStatus
    ticker: str
    trade_date: date
    timezone_label: str
    instrument: InstrumentIdentity
    market_move: MarketMove | None = None
    assessment: PrimaryAssessment
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    confidence: ConfidenceAssessment
    coverage_status: str
    trace: list[dict[str, str]] = Field(default_factory=list)

