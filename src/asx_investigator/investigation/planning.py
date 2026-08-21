"""Deterministic, bounded evidence-retrieval planning contracts."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
