"""Deterministic, bounded evidence-retrieval planning contracts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from asx_investigator.domain.models import InstrumentIdentity, IssuerReferenceFact, MarketMove

MAX_INITIAL_RETRIEVAL_TASKS = 10
MAX_RESULTS_PER_TASK = 5
MAX_DOCUMENT_BYTES_PER_TASK = 1_000_000
MAX_INITIAL_DOCUMENT_BYTES = 3_000_000


class DriverLane(StrEnum):
    ISSUER_DISCLOSURE = "ISSUER_DISCLOSURE"
    CAPITAL_AND_CORPORATE_ACTION = "CAPITAL_AND_CORPORATE_ACTION"
    INDEX_REBALANCE = "INDEX_REBALANCE"
    SECTOR_AND_PEER = "SECTOR_AND_PEER"
    COMMODITY_FX_MACRO = "COMMODITY_FX_MACRO"
    ANALYST_EVENT = "ANALYST_EVENT"
    NO_CATALYST_CONTROL = "NO_CATALYST_CONTROL"


class LaneSkip(BaseModel):
    """An auditable reason why a fixed driver lane was not acquired."""

    reason_code: Literal[
        "NOT_APPLICABLE",
        "NOT_ENTITLED",
        "PROVIDER_UNAVAILABLE",
        "BUDGET_EXHAUSTED",
        "POLICY_EXCLUDED",
    ]
    detail: str = Field(min_length=3, max_length=240)

    model_config = ConfigDict(frozen=True)


class RetrievalTask(BaseModel):
    """A sealed, provider-agnostic initial retrieval instruction."""

    task_id: str = Field(pattern=r"^R(?:[1-9]|10)$")
    lane: DriverLane
    tool: Literal["DISCOVER", "FETCH_OFFICIAL", "MARKET_CONTEXT"]
    query: str = Field(min_length=3, max_length=240)
    purpose: str = Field(min_length=10, max_length=240)
    max_results: int = Field(ge=1, le=MAX_RESULTS_PER_TASK)
    max_document_bytes: int = Field(ge=1, le=MAX_DOCUMENT_BYTES_PER_TASK)

    model_config = ConfigDict(frozen=True)


class RetrievalTaskResult(BaseModel):
    """Safe execution summary retained with a durable retrieval plan."""

    task_id: str = Field(pattern=r"^R(?:[1-9]|10)$")
    lane: DriverLane
    status: Literal["COMPLETE", "PARTIAL", "FAILED", "SKIPPED"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=MAX_RESULTS_PER_TASK)
    artifact_hashes: list[str] = Field(default_factory=list, max_length=MAX_RESULTS_PER_TASK)
    reason_code: str | None = Field(default=None, min_length=3, max_length=120)

    @model_validator(mode="after")
    def validate_status_detail(self) -> RetrievalTaskResult:
        if self.status in {"FAILED", "SKIPPED"} and self.reason_code is None:
            raise ValueError("failed or skipped retrieval result requires a reason_code")
        if self.status == "COMPLETE" and self.reason_code is not None:
            raise ValueError("complete retrieval result cannot carry a reason_code")
        return self

    model_config = ConfigDict(frozen=True)


class RetrievalPlan(BaseModel):
    """Bounded initial acquisition plan plus a single optional model follow-up."""

    policy_version: str = Field(min_length=1, max_length=80)
    tasks: list[RetrievalTask] = Field(min_length=1, max_length=MAX_INITIAL_RETRIEVAL_TASKS)
    skipped_lanes: dict[DriverLane, LaneSkip]
    follow_up_calls_remaining: Literal[1] = 1

    @model_validator(mode="after")
    def validate_coverage_and_budget(self) -> RetrievalPlan:
        task_ids = [item.task_id for item in self.tasks]
        if task_ids != [f"R{index}" for index in range(1, len(task_ids) + 1)]:
            raise ValueError("retrieval task IDs must be deterministic and contiguous")
        active_lanes = [item.lane for item in self.tasks]
        if len(active_lanes) != len(set(active_lanes)):
            raise ValueError("retrieval plan permits one initial task per driver lane")
        active = set(active_lanes)
        skipped = set(self.skipped_lanes)
        if active & skipped or active | skipped != set(DriverLane):
            raise ValueError("every driver lane must be active or skipped exactly once")
        if sum(item.max_document_bytes for item in self.tasks) > MAX_INITIAL_DOCUMENT_BYTES:
            raise ValueError("initial document byte budget exceeds the fixed maximum")
        return self

    @property
    def initial_provider_calls(self) -> int:
        return len(self.tasks)

    @property
    def plan_hash(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    model_config = ConfigDict(frozen=True)


class RetrievalPlanner:
    """Select a small fixed retrieval surface from observable case inputs.

    Shared issuer facts are treated as typed routing flags.  Their values are
    deliberately never interpolated into a provider query or model packet.
    """

    policy_version = "retrieval-policy-v1"

    _BASE_LANES = (
        DriverLane.ISSUER_DISCLOSURE,
        DriverLane.INDEX_REBALANCE,
        DriverLane.SECTOR_AND_PEER,
        DriverLane.NO_CATALYST_CONTROL,
    )
    _QUERIES = {
        DriverLane.ISSUER_DISCLOSURE: "{ticker} ASX announcement {trade_date}",
        DriverLane.CAPITAL_AND_CORPORATE_ACTION: (
            "{ticker} ASX capital raising dividend split {trade_date}"
        ),
        DriverLane.INDEX_REBALANCE: (
            "{ticker} ASX index rebalance inclusion deletion {trade_date}"
        ),
        DriverLane.SECTOR_AND_PEER: "{ticker} ASX sector peer read-through {trade_date}",
        DriverLane.COMMODITY_FX_MACRO: "{ticker} ASX commodity FX macro {trade_date}",
        DriverLane.NO_CATALYST_CONTROL: "{ticker} ASX unusual trading news {trade_date}",
    }
    _PURPOSES = {
        DriverLane.ISSUER_DISCLOSURE: "Discover contemporaneous issuer disclosure candidates.",
        DriverLane.CAPITAL_AND_CORPORATE_ACTION: "Discover capital or corporate-action candidates.",
        DriverLane.INDEX_REBALANCE: "Discover official index rebalance candidates.",
        DriverLane.SECTOR_AND_PEER: "Discover sector and peer read-through candidates.",
        DriverLane.COMMODITY_FX_MACRO: "Discover commodity, FX and macro driver candidates.",
        DriverLane.NO_CATALYST_CONTROL: "Search bounded coverage before a no-catalyst outcome.",
    }

    def build(
        self,
        *,
        instrument: InstrumentIdentity,
        session_date: object,
        move: MarketMove,
        context_facts: list[IssuerReferenceFact],
    ) -> RetrievalPlan:
        """Create a repeatable plan without trusting free-form context values."""

        fields = {item.field.lower().strip() for item in context_facts}
        active = list(self._BASE_LANES)
        if move.is_unusual or (move.volume_zscore is not None and move.volume_zscore >= 2):
            active.insert(1, DriverLane.CAPITAL_AND_CORPORATE_ACTION)
        if fields & {"commodity_exposure", "currency_exposure"}:
            active.append(DriverLane.COMMODITY_FX_MACRO)

        # `session_date` comes from a validated ASX session upstream.  The
        # string form is deterministic and has no model or memory content.
        date_text = str(session_date)
        tasks = [
            RetrievalTask(
                task_id=f"R{index}",
                lane=lane,
                tool="DISCOVER",
                query=self._QUERIES[lane].format(
                    ticker=instrument.asx_code.upper().strip(), trade_date=date_text
                ),
                purpose=self._PURPOSES[lane],
                max_results=5,
                max_document_bytes=400_000,
            )
            for index, lane in enumerate(active, start=1)
        ]
        skipped: dict[DriverLane, LaneSkip] = {}
        for lane in DriverLane:
            if lane in active:
                continue
            if lane == DriverLane.ANALYST_EVENT:
                skipped[lane] = LaneSkip(
                    reason_code="NOT_ENTITLED",
                    detail="No approved original-research acquisition source is configured.",
                )
            elif lane == DriverLane.COMMODITY_FX_MACRO:
                skipped[lane] = LaneSkip(
                    reason_code="NOT_APPLICABLE",
                    detail="No approved commodity or currency exposure routing flag exists.",
                )
            else:  # defensive: every current lane is either active or explicitly skipped
                skipped[lane] = LaneSkip(
                    reason_code="NOT_APPLICABLE",
                    detail="No deterministic retrieval trigger exists for this case.",
                )
        return RetrievalPlan(
            policy_version=self.policy_version,
            tasks=tasks,
            skipped_lanes=skipped,
        )
