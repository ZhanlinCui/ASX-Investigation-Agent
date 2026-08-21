from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from asx_investigator.agent.reasoning import ChallengeResult, HypothesisBatch
from asx_investigator.domain.models import (
    CoverageGap,
    EvidenceItem,
    InstrumentIdentity,
    LedgerEntry,
    MarketMove,
    SourceConflict,
    TradingSession,
    ValidationResult,
)
from asx_investigator.evidence.context import EvidencePacket
from asx_investigator.investigation.ledger import (
    LEDGER_SCHEMA_VERSION,
    LedgerBuilder,
    LedgerIntegrityError,
)
from asx_investigator.investigation.planning import RetrievalPlan, RetrievalTaskResult
from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.market import CorporateAction, MarketDataResult
from asx_investigator.providers.outcomes import ProviderOutcome

CHECKPOINT_POLICY_VERSION = "phase5-p5.1-v1"
CHECKPOINT_SCHEMA_VERSION = "checkpoint-v3"

DURABLE_STAGE_ORDER = (
    "resolve_instrument",
    "resolve_asx_session",
    "acquire_market_data",
    "test_mechanical_explanations",
    "discover_and_freeze_documents",
    "extract_exact_passages",
    "assemble_evidence_packet",
    "generate_ranked_hypotheses",
    "targeted_retrieval",
    "challenge_leading_hypothesis",
    "deterministic_validation",
)


def _normalized_hash(value: str) -> str:
    if len(value) == 64 and all(character in "0123456789abcdef" for character in value):
        return value
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _unique_hashes(values: list[str]) -> list[str]:
    return sorted(set(values))


def _state_hash(stage: str, value: object) -> str:
    """Hash a deterministic JSON representation without including checkpoint metadata."""

    def normalize(item: object) -> object:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        if isinstance(item, list):
            return [normalize(entry) for entry in item]
        if isinstance(item, dict):
            return {str(key): normalize(entry) for key, entry in item.items()}
        return item

    payload = json.dumps(
        {"stage": stage, "state": normalize(value)},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class MarketDataCheckpoint(BaseModel):
    """Only the JSON-safe market state needed after the provider boundary."""

    bars: list[DailyBar]
    selected_provider: str
    outcomes: list[ProviderOutcome[list[DailyBar]]]
    conflicts: list[SourceConflict] = Field(default_factory=list)
    coverage_gap: CoverageGap | None = None
    benchmark_return: float | None = None
    market_move: MarketMove

    def to_result(self) -> MarketDataResult:
        return MarketDataResult(
            bars=self.bars,
            selected_provider=self.selected_provider,
            outcomes=self.outcomes,
            conflicts=self.conflicts,
            coverage_gap=self.coverage_gap,
        )


class InvestigationState(BaseModel):
    """Durable investigation values; runtime clients and exceptions never enter this model."""

    version_id: str
    request_artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    initial_input_artifact_hashes: list[str] = Field(min_length=1)
    stage_output_artifact_hashes: dict[str, list[str]] = Field(default_factory=dict)
    ledger_stage_output_hashes: dict[str, list[str]] = Field(default_factory=dict)
    ledger_schema_version: str | None = None
    completed_stage: str | None = None
    instrument: InstrumentIdentity | None = None
    session: TradingSession | None = None
    market_data: MarketDataCheckpoint | None = None
    corporate_actions: ProviderOutcome[list[CorporateAction]] | None = None
    retrieval_plan: RetrievalPlan | None = None
    retrieval_results: list[RetrievalTaskResult] = Field(default_factory=list)
    evidence: list[EvidenceItem] | None = None
    coverage_complete: bool | None = None
    coverage_gaps: list[CoverageGap] | None = None
    conflicts: list[SourceConflict] | None = None
    packet: EvidencePacket | None = None
    hypothesis_batch: HypothesisBatch | None = None
    targeted_assertion_ids: list[str] = Field(default_factory=list)
    challenge: ChallengeResult | None = None
    validations: list[ValidationResult] = Field(default_factory=list)
    ledger: list[LedgerEntry] = Field(default_factory=list)
    trace: list[dict[str, str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_completed_state(self) -> InvestigationState:
        if self.request_artifact_hash not in self.initial_input_artifact_hashes:
            raise ValueError("checkpoint inputs must include the sealed request artifact")
        if self.completed_stage is None:
            return self
        if self.completed_stage not in DURABLE_STAGE_ORDER:
            raise ValueError("checkpoint completed_stage is not durable")
        if self.completed_stage not in self.stage_output_artifact_hashes:
            raise ValueError("checkpoint is missing frozen output hashes for its stage")
        boundary = DURABLE_STAGE_ORDER.index(self.completed_stage)
        introduced_at = {
            "instrument": "resolve_instrument",
            "session": "resolve_asx_session",
            "market_data": "acquire_market_data",
            "corporate_actions": "test_mechanical_explanations",
            "evidence": "discover_and_freeze_documents",
            "coverage_complete": "extract_exact_passages",
            "coverage_gaps": "extract_exact_passages",
            "conflicts": "extract_exact_passages",
            "packet": "assemble_evidence_packet",
            "hypothesis_batch": "generate_ranked_hypotheses",
            "challenge": "challenge_leading_hypothesis",
        }
        required_state = [
            name
            for name, stage in introduced_at.items()
            if DURABLE_STAGE_ORDER.index(stage) <= boundary
        ]
        missing = [name for name in required_state if getattr(self, name) is None]
        if missing:
            raise ValueError(f"checkpoint is missing completed state: {', '.join(missing)}")
        if (
            boundary >= DURABLE_STAGE_ORDER.index("test_mechanical_explanations")
            and not self.validations
        ):
            raise ValueError("checkpoint is missing completed mechanical validations")
        future = [
            name
            for name, stage in introduced_at.items()
            if getattr(self, name) is not None and DURABLE_STAGE_ORDER.index(stage) > boundary
        ]
        if self.validations and boundary < DURABLE_STAGE_ORDER.index(
            "test_mechanical_explanations"
        ):
            future.append("validations")
        if future:
            raise ValueError(
                f"checkpoint contains state beyond its completed stage: {', '.join(future)}"
            )
        invalid_output_stages = [
            stage
            for stage in self.stage_output_artifact_hashes
            if stage not in DURABLE_STAGE_ORDER
            or DURABLE_STAGE_ORDER.index(stage) > boundary
        ]
        if invalid_output_stages:
            raise ValueError("checkpoint contains output hashes beyond its completed stage")
        required_output_stages = DURABLE_STAGE_ORDER[: boundary + 1]
        missing_output_stages = [
            stage
            for stage in required_output_stages
            if stage not in self.stage_output_artifact_hashes
        ]
        if missing_output_stages:
            raise ValueError("checkpoint is missing prior stage output hashes")
        for stage in required_output_stages:
            if self.output_hashes(stage) != self._derived_output_hashes(stage):
                raise ValueError("checkpoint output hashes do not match completed state")
        self._validate_ledger(boundary)
        return self

    def _validate_ledger(self, boundary: int) -> None:
        """Require a complete ledger whenever a checkpoint has begun emitting one."""

        if self.ledger_schema_version is None:
            if self.ledger or self.ledger_stage_output_hashes:
                raise ValueError("checkpoint ledger is missing its schema marker")
            return
        if self.ledger_schema_version != LEDGER_SCHEMA_VERSION:
            raise ValueError("checkpoint ledger schema is not supported")
        if not self.ledger:
            raise ValueError("checkpoint ledger is missing its required entries")
        try:
            LedgerBuilder(self.ledger)
        except LedgerIntegrityError as error:
            raise ValueError(f"checkpoint ledger is invalid: {error}") from error
        stage_entries = [entry for entry in self.ledger if entry.status != "RESUMED"]
        completed_stages = [entry.stage for entry in stage_entries]
        expected_stages = list(DURABLE_STAGE_ORDER[: boundary + 1])
        if completed_stages != expected_stages:
            raise ValueError("checkpoint ledger completed stages do not match state")
        for entry in self.ledger:
            if entry.status not in {"COMPLETED", "RESUMED", "SKIPPED"}:
                raise ValueError("checkpoint ledger has an unsupported entry status")
            if entry.stage not in DURABLE_STAGE_ORDER:
                raise ValueError("checkpoint ledger has an unknown stage")
            if DURABLE_STAGE_ORDER.index(entry.stage) > boundary:
                raise ValueError("checkpoint ledger contains a future stage")
            if entry.input_hashes != self.ledger_input_hashes(entry.stage):
                raise ValueError("checkpoint ledger input hashes do not match state")
            if entry.output_hashes != self.ledger_output_hashes(entry.stage):
                raise ValueError("checkpoint ledger output hashes do not match state")

    def complete(self, stage: str) -> None:
        if stage not in DURABLE_STAGE_ORDER:
            raise ValueError(f"{stage} is not a durable checkpoint stage")
        boundary = DURABLE_STAGE_ORDER.index(stage)
        self.stage_output_artifact_hashes = {
            **self.stage_output_artifact_hashes,
            **{
                earlier_stage: self._derived_output_hashes(earlier_stage)
                for earlier_stage in DURABLE_STAGE_ORDER[:boundary]
                if earlier_stage not in self.stage_output_artifact_hashes
            },
            stage: self._derived_output_hashes(stage),
        }
        self.completed_stage = stage

    def capture_ledger_output(self, stage: str) -> None:
        if stage not in DURABLE_STAGE_ORDER:
            raise ValueError(f"{stage} is not a durable checkpoint stage")
        if stage in self.ledger_stage_output_hashes:
            return
        self.ledger_stage_output_hashes = {
            **self.ledger_stage_output_hashes,
            stage: self._derived_ledger_output_hashes(stage),
        }

    def has_completed(self, stage: str) -> bool:
        if self.completed_stage is None:
            return False
        return DURABLE_STAGE_ORDER.index(self.completed_stage) >= DURABLE_STAGE_ORDER.index(stage)

    def _derived_output_hashes(self, stage: str | None) -> list[str]:
        hashes: list[str] = []
        if stage == "acquire_market_data" and self.market_data is not None:
            hashes.extend(
                outcome.artifact.sha256
                for outcome in self.market_data.outcomes
                if outcome.artifact is not None
            )
        elif stage == "test_mechanical_explanations":
            if self.corporate_actions and self.corporate_actions.artifact is not None:
                hashes.append(self.corporate_actions.artifact.sha256)
        elif stage in {"discover_and_freeze_documents", "targeted_retrieval"}:
            hashes.extend(
                _normalized_hash(item.content_hash) for item in self.evidence or []
            )
            if stage == "targeted_retrieval":
                hashes = list(
                    set(hashes)
                    - set(
                        self.stage_output_artifact_hashes.get(
                            "discover_and_freeze_documents", []
                        )
                    )
                )
        return _unique_hashes(hashes)

    def output_hashes(self, stage: str | None = None) -> list[str]:
        selected_stage = stage or self.completed_stage
        if selected_stage is None:
            return []
        return _unique_hashes(
            self.stage_output_artifact_hashes.get(selected_stage, [])
        )

    def input_hashes(self, stage: str | None = None) -> list[str]:
        selected_stage = stage or self.completed_stage
        if selected_stage is None:
            return _unique_hashes(self.initial_input_artifact_hashes)
        try:
            boundary = DURABLE_STAGE_ORDER.index(selected_stage)
        except ValueError as error:
            raise ValueError(f"{selected_stage} is not a durable checkpoint stage") from error
        hashes = list(self.initial_input_artifact_hashes)
        for earlier_stage in DURABLE_STAGE_ORDER[:boundary]:
            hashes.extend(self.output_hashes(earlier_stage))
        return _unique_hashes(hashes)

    def ledger_output_hashes(self, stage: str) -> list[str]:
        if stage not in DURABLE_STAGE_ORDER:
            raise ValueError(f"{stage} is not a durable checkpoint stage")
        if stage not in self.ledger_stage_output_hashes:
            raise ValueError(f"ledger output was not captured for {stage}")
        return list(self.ledger_stage_output_hashes[stage])

    def _derived_ledger_output_hashes(self, stage: str) -> list[str]:
        values: dict[str, object] = {
            "resolve_instrument": self.instrument,
            "resolve_asx_session": self.session,
            "acquire_market_data": self.market_data,
            "test_mechanical_explanations": {
                "corporate_actions": self.corporate_actions,
                "validations": self.validations,
            },
            "discover_and_freeze_documents": self.evidence,
            "extract_exact_passages": {
                "coverage_complete": self.coverage_complete,
                "coverage_gaps": self.coverage_gaps,
                "conflicts": self.conflicts,
            },
            "assemble_evidence_packet": self.packet,
            "generate_ranked_hypotheses": self.hypothesis_batch,
            "targeted_retrieval": {
                "evidence": self.evidence,
                "packet": self.packet,
                "targeted_assertion_ids": self.targeted_assertion_ids,
            },
            "challenge_leading_hypothesis": self.challenge,
            "deterministic_validation": self.validations,
        }
        return [_state_hash(stage, values[stage])]

    def ledger_input_hashes(self, stage: str) -> list[str]:
        if stage not in DURABLE_STAGE_ORDER:
            raise ValueError(f"{stage} is not a durable checkpoint stage")
        boundary = DURABLE_STAGE_ORDER.index(stage)
        hashes = list(self.initial_input_artifact_hashes)
        for earlier_stage in DURABLE_STAGE_ORDER[:boundary]:
            hashes.extend(self.ledger_output_hashes(earlier_stage))
        return _unique_hashes(hashes)


class CheckpointEnvelope(BaseModel):
    """Durable, typed state from a completed investigation stage."""

    version_id: str
    stage: str
    input_artifact_hashes: list[str]
    output_artifact_hashes: list[str]
    typed_state_json: dict[str, object]
    schema_version: str = CHECKPOINT_SCHEMA_VERSION
    policy_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model_config = ConfigDict(frozen=True)
