from __future__ import annotations

import pytest
from pydantic import ValidationError

from asx_investigator.investigation.planning import (
    DriverLane,
    LaneSkip,
    RetrievalPlan,
    RetrievalTask,
)


def task(*, task_id: str = "R1", lane: DriverLane = DriverLane.ISSUER_DISCLOSURE) -> RetrievalTask:
    return RetrievalTask(
        task_id=task_id,
        lane=lane,
        tool="DISCOVER",
        query="BHP ASX announcement 2026-08-20",
        purpose="Find contemporaneous issuer disclosure candidates.",
        max_results=3,
        max_document_bytes=120_000,
    )


def skipped_for(*active: DriverLane) -> dict[DriverLane, LaneSkip]:
    return {
        lane: LaneSkip(reason_code="NOT_APPLICABLE", detail="No deterministic trigger.")
        for lane in DriverLane
        if lane not in active
    }


def task_payload(**overrides: object) -> dict[str, object]:
    payload = task().model_dump()
    payload.update(overrides)
    return payload


def test_retrieval_plan_is_deterministic_and_declares_every_inactive_lane() -> None:
    first = RetrievalPlan(
        policy_version="retrieval-policy-v1",
        tasks=[task()],
        skipped_lanes=skipped_for(DriverLane.ISSUER_DISCLOSURE),
    )
    second = RetrievalPlan(
        policy_version="retrieval-policy-v1",
        tasks=[task()],
        skipped_lanes=skipped_for(DriverLane.ISSUER_DISCLOSURE),
    )

    assert first.plan_hash == second.plan_hash
    assert first.follow_up_calls_remaining == 1
    assert first.initial_provider_calls == 1
    assert set(first.skipped_lanes) | {item.lane for item in first.tasks} == set(DriverLane)


def test_retrieval_plan_rejects_unknown_tools_oversized_queries_and_unbounded_budgets() -> None:
    with pytest.raises(ValidationError, match="tool"):
        RetrievalTask.model_validate(task_payload(tool="BROWSER"))

    with pytest.raises(ValidationError, match="query"):
        RetrievalTask.model_validate(task_payload(query="x" * 241))

    with pytest.raises(ValidationError, match="max_document_bytes"):
        RetrievalTask.model_validate(task_payload(max_document_bytes=1_000_001))

    with pytest.raises(ValidationError, match="initial document byte budget"):
        RetrievalPlan(
            policy_version="retrieval-policy-v1",
            tasks=[
                RetrievalTask.model_validate(
                    task_payload(
                        task_id=f"R{index}",
                        lane=lane,
                        max_document_bytes=1_000_000,
                    )
                )
                for index, lane in enumerate(DriverLane, start=1)
            ],
            skipped_lanes={},
        )


def test_retrieval_plan_rejects_duplicate_lanes_and_missing_skip_reasons() -> None:
    with pytest.raises(ValidationError, match="one initial task"):
        RetrievalPlan(
            policy_version="retrieval-policy-v1",
            tasks=[task(task_id="R1"), task(task_id="R2")],
            skipped_lanes=skipped_for(DriverLane.ISSUER_DISCLOSURE),
        )

    with pytest.raises(ValidationError, match="active or skipped"):
        RetrievalPlan(
            policy_version="retrieval-policy-v1",
            tasks=[task()],
            skipped_lanes={},
        )
