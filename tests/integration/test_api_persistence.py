from pathlib import Path
from time import sleep

from fastapi.testclient import TestClient

from asx_investigator.api.app import create_app
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.storage.repository import SQLiteCaseRepository


def wait_for_report(client: TestClient, case_id: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    for _ in range(30):
        response = client.get(f"/api/v1/investigations/{case_id}")
        payload = response.json()
        if payload["status"] not in {"QUEUED", "RUNNING"}:
            return payload
        sleep(0.01)
    raise AssertionError(f"case did not complete: {payload}")


def test_case_survives_app_restart_and_appears_in_archive(tmp_path: Path) -> None:
    database_path = tmp_path / "cases.db"
    service = InvestigationService(RecordedToolGateway.default())
    first_app = create_app(service, repository=SQLiteCaseRepository(database_path))
    with TestClient(first_app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        ).json()
        report = wait_for_report(client, accepted["case_id"])
        assert report["status"] == "COMPLETED"

    second_app = create_app(service, repository=SQLiteCaseRepository(database_path))
    with TestClient(second_app) as client:
        restored = client.get(f"/api/v1/investigations/{accepted['case_id']}")
        archive = client.get("/api/v1/investigations")

    assert restored.status_code == 200
    assert restored.json()["assessment"]["primary_claim_id"] == "C1"
    assert [item["case_id"] for item in archive.json()["items"]] == [accepted["case_id"]]


def test_refinement_creates_child_version_without_mutating_parent(tmp_path: Path) -> None:
    app = create_app(
        InvestigationService(RecordedToolGateway.default()),
        repository=SQLiteCaseRepository(tmp_path / "cases.db"),
    )
    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        ).json()
        parent = wait_for_report(client, accepted["case_id"])
        child_response = client.post(
            f"/api/v1/investigations/{accepted['case_id']}/versions",
            json={"primary_only": True, "excluded_evidence_ids": []},
        )
        child = child_response.json()

    assert child_response.status_code == 202
    assert child["version_id"] != accepted["version_id"]
    assert child["parent_version_id"] == accepted["version_id"]
    assert child["version_number"] == 2
    assert parent["case_version"] == 1


def test_refinement_excludes_named_evidence_in_the_child_only(tmp_path: Path) -> None:
    app = create_app(
        InvestigationService(RecordedToolGateway.default()),
        repository=SQLiteCaseRepository(tmp_path / "cases.db"),
    )
    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        ).json()
        parent = wait_for_report(client, accepted["case_id"])
        child = client.post(
            f"/api/v1/investigations/{accepted['case_id']}/versions",
            json={"excluded_evidence_ids": ["E1"]},
        ).json()
        child_report = wait_for_report(client, accepted["case_id"])

    assert child["parent_version_id"] == accepted["version_id"]
    assert parent["outcome"] == "EXPLAINED"
    assert [item["evidence_id"] for item in parent["evidence"]] == ["E1"]
    assert child_report["outcome"] == "INSUFFICIENT_EVIDENCE"
    assert child_report["evidence"] == []
    assert child_report["coverage_status"] == "SCOPED_REFINEMENT"


def test_stage_checkpoints_are_persisted_with_monotonic_sequences(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    app = create_app(
        InvestigationService(RecordedToolGateway.default()),
        repository=repository,
    )
    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        ).json()
        report = wait_for_report(client, accepted["case_id"])

    import asyncio

    events = asyncio.run(repository.list_events(accepted["version_id"]))
    sequences = [event.sequence for event in events]
    stages = {event.stage for event in events}

    assert sequences == list(range(1, len(sequences) + 1))
    assert "generate_ranked_hypotheses" not in stages
    assert {"acquire_market_data", "deterministic_validation", "persist_and_publish"} <= stages
    assert report["trace_reference"]["last_sequence"] < sequences[-1]


def test_sse_replays_only_events_after_last_event_id(tmp_path: Path) -> None:
    app = create_app(
        InvestigationService(RecordedToolGateway.default()),
        repository=SQLiteCaseRepository(tmp_path / "cases.db"),
    )
    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        ).json()
        wait_for_report(client, accepted["case_id"])
        replay = client.get(
            f"/api/v1/investigations/{accepted['case_id']}/events",
            headers={"Last-Event-ID": "2"},
        )

    event_ids = [
        int(line.removeprefix("id: "))
        for line in replay.text.splitlines()
        if line.startswith("id: ")
    ]
    assert replay.status_code == 200
    assert event_ids
    assert min(event_ids) == 3
