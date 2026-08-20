from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class CausalMechanism(StrEnum):
    MECHANICAL = "MECHANICAL"
    ISSUER_EVENT = "ISSUER_EVENT"
    SECTOR_READTHROUGH = "SECTOR_READTHROUGH"
    COMMODITY_FX = "COMMODITY_FX"
    MACRO_MARKET = "MACRO_MARKET"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    UNKNOWN = "UNKNOWN"


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


class EvidenceAssertion(BaseModel):
    """Extractive, case-scoped evidence available to causal reasoning."""

    assertion_id: str = Field(pattern=r"^A[1-9][0-9]*$")
    evidence_id: str
    case_version_id: str = Field(min_length=1)
    exact_text: str = Field(min_length=1, max_length=1_800)
    span_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at: datetime
    retrieved_at: datetime
    source_authority: str = Field(min_length=1, max_length=80)
    locator: str | None = Field(default=None, max_length=520)
    role: EvidenceRole
    causal_eligible: bool
    mechanism_hint: CausalMechanism = CausalMechanism.UNKNOWN
    normalized_entities: list[str] = Field(default_factory=list)
    normalized_values: dict[str, float] = Field(default_factory=dict)
    contradicting_assertion_ids: list[str] = Field(default_factory=list)


class MechanismTest(BaseModel):
    test_id: str = Field(pattern=r"^MT-[A-Z0-9_-]+$")
    mechanism: CausalMechanism
    status: ValidationStatus
    summary: str = Field(min_length=1, max_length=520)
    taxonomy_version: str = Field(min_length=1, max_length=80)
    policy_version: str = Field(min_length=1, max_length=80)
    created_at: datetime
    supporting_assertion_ids: list[str] = Field(default_factory=list)
    contradicting_assertion_ids: list[str] = Field(default_factory=list)


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


class CheckpointSummary(BaseModel):
    stage: str
    created_at: datetime
    input_artifact_hashes: list[str] = Field(default_factory=list)
    output_artifact_hashes: list[str] = Field(default_factory=list)
    schema_version: str
    policy_version: str


class LedgerEntry(BaseModel):
    sequence: int = Field(ge=1)
    stage: str = Field(min_length=1)
    status: str = Field(min_length=1)
    input_hashes: list[str] = Field(default_factory=list)
    output_hashes: list[str] = Field(default_factory=list)
    schema_version: str = Field(min_length=1, max_length=80)
    policy_version: str = Field(min_length=1)
    model_configuration: dict[str, str] = Field(default_factory=dict)
    validation_status: ValidationStatus | None = None
    validation_summary: str | None = Field(default=None, max_length=520)
    created_at: datetime


class SharedMemoryEntry(BaseModel):
    """An admitted shared-memory record; it is never case reasoning input by itself."""

    entry_id: str = Field(min_length=1, max_length=80)
    memory_type: str = Field(min_length=1, max_length=80)
    ticker: str | None = Field(default=None, min_length=2, max_length=12)
    payload: dict[str, object] = Field(default_factory=dict)
    source_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_url: str | None = Field(default=None, min_length=1, max_length=2_000)
    scope: str = Field(min_length=1, max_length=80)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    policy_version: str = Field(min_length=1, max_length=80)
    created_at: datetime
    revoked_at: datetime | None = None

    @model_validator(mode="after")
    def validate_validity_range(self) -> SharedMemoryEntry:
        for name, value in (
            ("valid_from", self.valid_from),
            ("valid_until", self.valid_until),
            ("created_at", self.created_at),
            ("revoked_at", self.revoked_at),
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must include a timezone")
        if self.valid_from and self.valid_until and self.valid_from >= self.valid_until:
            raise ValueError("valid_from must be before valid_until")
        return self


class IssuerReferenceFact(BaseModel):
    """The only shared-memory value allowed into a reasoning packet."""

    entry_id: str = Field(min_length=1, max_length=80)
    ticker: str = Field(min_length=2, max_length=12)
    field: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=2_000)
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_url: str = Field(min_length=1, max_length=2_000)
    scope: Literal["CONTEXT_ONLY"] = "CONTEXT_ONLY"
    valid_from: datetime | None = None
    valid_until: datetime
    policy_version: str = Field(min_length=1, max_length=80)
    created_at: datetime

    @model_validator(mode="after")
    def validate_reference_validity(self) -> IssuerReferenceFact:
        self.ticker = self.ticker.upper().strip()
        for name, value in (
            ("valid_from", self.valid_from),
            ("valid_until", self.valid_until),
            ("created_at", self.created_at),
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError(f"{name} must include a timezone")
        if self.valid_from and self.valid_from >= self.valid_until:
            raise ValueError("valid_from must be before valid_until")
        return self

    @property
    def ledger_hash(self) -> str:
        """Hash the admissible entry identity without exposing its text in the ledger."""

        value = f"shared-memory:{self.entry_id}:{self.source_hash}"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()


class BandCalibrationMetadata(BaseModel):
    eligible_cases: int = Field(ge=0)
    correct_cases: int = Field(ge=0)
    acceptable_alternative_cases: int = Field(ge=0)
    abstained_cases: int = Field(ge=0)
    material_errors: int = Field(ge=0)
    status: str = Field(min_length=1)
    observed_correct_proportion: float = Field(default=0.0, ge=0, le=1)
    observed_acceptable_alternative_proportion: float = Field(default=0.0, ge=0, le=1)
    observed_abstention_proportion: float = Field(default=0.0, ge=0, le=1)

    @model_validator(mode="after")
    def validate_counts_and_compute_proportions(self) -> BandCalibrationMetadata:
        counts = {
            "correct_cases": self.correct_cases,
            "acceptable_alternative_cases": self.acceptable_alternative_cases,
            "abstained_cases": self.abstained_cases,
            "material_errors": self.material_errors,
        }
        for name, count in counts.items():
            if count > self.eligible_cases:
                raise ValueError(f"{name} cannot exceed eligible_cases")
        if (
            self.correct_cases
            + self.acceptable_alternative_cases
            + self.abstained_cases
            + self.material_errors
            > self.eligible_cases
        ):
            raise ValueError(
                "calibration outcome counts cannot exceed eligible_cases"
            )
        if not self.eligible_cases:
            if any(
                (
                    self.observed_correct_proportion,
                    self.observed_acceptable_alternative_proportion,
                    self.observed_abstention_proportion,
                )
            ):
                raise ValueError("zero eligible cases require zero observed proportions")
            return self
        self.observed_correct_proportion = self.correct_cases / self.eligible_cases
        self.observed_acceptable_alternative_proportion = (
            self.acceptable_alternative_cases / self.eligible_cases
        )
        self.observed_abstention_proportion = self.abstained_cases / self.eligible_cases
        return self


class CalibrationMetadata(BaseModel):
    label: str = "Evidence-strength band calibration"
    status: str = "NOT_RUN"
    corpus_version: str | None = None
    confidence_rule_version: str | None = None
    created_at: datetime | None = None
    creation_commit: str | None = Field(default=None, pattern=r"^[0-9a-f]{7,64}$")
    bands: dict[str, BandCalibrationMetadata] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_artifact_provenance(self) -> CalibrationMetadata:
        if (self.created_at is None) != (self.creation_commit is None):
            raise ValueError(
                "calibration created_at and creation_commit must be recorded together"
            )
        if self.status != "NOT_RUN" and (
            self.created_at is None
            or self.creation_commit is None
            or self.corpus_version is None
            or self.confidence_rule_version is None
        ):
            raise ValueError(
                "measured calibration metadata requires corpus, rule and creation provenance"
            )
        return self


class ProviderCallDiagnostic(BaseModel):
    provider: str
    operation: str
    status: str
    coverage: str
    retrieved_at: datetime
    provenance: dict[str, str] = Field(default_factory=dict)
    error_code: str | None = None
    source_version: str | None = None
    artifact_id: str | None = None


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
    provider_diagnostics: list[ProviderCallDiagnostic] = Field(default_factory=list)
    artifact_hashes: list[str] = Field(default_factory=list)
    checkpoint_lineage: list[CheckpointSummary] = Field(default_factory=list)
    assertions: list[EvidenceAssertion] = Field(default_factory=list)
    mechanism_tests: list[MechanismTest] = Field(default_factory=list)
    ledger: list[LedgerEntry] = Field(default_factory=list)
    calibration_metadata: CalibrationMetadata = Field(default_factory=CalibrationMetadata)
    trace_reference: TraceReference | None = None
    parent_case_id: str | None = None
    parent_version_id: str | None = None
    case_version: int = Field(default=1, ge=1)
    trace: list[dict[str, str]] = Field(default_factory=list)
