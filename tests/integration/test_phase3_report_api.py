from time import sleep

from fastapi.testclient import TestClient

from asx_investigator.api.app import create_app
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.storage.repository import SQLiteCaseRepository


def _completed_recorded_case(client: TestClient) -> tuple[str, dict[str, object]]:
    accepted = client.post(
        "/api/v1/investigations",
        json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
    ).json()
    case_id = accepted["case_id"]
    body: dict[str, object] = {}
    for _ in range(80):
        body = client.get(f"/api/v1/investigations/{case_id}").json()
        if body["status"] == "COMPLETED":
            return case_id, body
        sleep(0.01)
    raise AssertionError("recorded investigation did not complete")


def test_completed_report_exposes_only_auditable_phase3_decision_records(tmp_path) -> None:
    app = create_app(
        InvestigationService(RecordedToolGateway.default()),
        repository=SQLiteCaseRepository(tmp_path / "cases.db"),
    )
    with TestClient(app) as client:
        case_id, body = _completed_recorded_case(client)
        markdown = client.get(
            f"/api/v1/investigations/{case_id}?format=markdown"
        ).text

    assertions = body["assertions"]
    mechanism_tests = body["mechanism_tests"]
    ledger = body["ledger"]
    calibration = body["calibration_metadata"]

    assert assertions[0]["span_hash"]
    assert assertions[0]["artifact_hash"]
    assert mechanism_tests[0]["mechanism"] == "MECHANICAL"
    assert ledger[-1]["status"] == "COMPLETED"
    assert ledger[-1]["policy_version"]
    assert calibration["status"] == "NOT_RUN"
    assert "probability" not in calibration["label"].lower()
    assert "case_version_id" not in assertions[0]
    assert set(ledger[-1]) == {
        "sequence",
        "stage",
        "status",
        "input_hashes",
        "output_hashes",
        "schema_version",
        "policy_version",
        "validation_status",
        "created_at",
    }
    assert all("observed_correct_proportion" not in item for item in calibration["bands"].values())

    assert "## Evidence assertions" in markdown
    assert "## Mechanism tests" in markdown
    assert "## Decision ledger" in markdown
    assert "## Calibration sample status" in markdown
    assert "raw provider response" not in markdown.lower()
    assert "chain of thought" not in markdown.lower()
