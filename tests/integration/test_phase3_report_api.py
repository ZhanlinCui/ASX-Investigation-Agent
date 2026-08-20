import asyncio
import json
import sqlite3
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


def test_public_case_surfaces_fail_closed_while_scoped_evidence_remains_available(
    tmp_path,
) -> None:
    """The public boundary must not inherit arbitrary persisted report fields."""

    marker = "PRIVATE-REPORT-MARKER-DO-NOT-PUBLISH"
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    app = create_app(
        InvestigationService(RecordedToolGateway.default()), repository=repository
    )
    with TestClient(app) as client:
        case_id, completed = _completed_recorded_case(client)
        version_id = str(completed["run_id"])
        _inject_private_markers(repository, version_id, marker)
        asyncio.run(
            repository.append_event(
                version_id,
                "stage",
                "private_stage",
                "COMPLETED",
                {"untrusted_payload": marker},
            )
        )

        report = client.get(f"/api/v1/investigations/{case_id}")
        archive = client.get("/api/v1/investigations")
        versions = client.get(f"/api/v1/investigations/{case_id}/versions")
        events = client.get(f"/api/v1/investigations/{case_id}/events")
        markdown = client.get(
            f"/api/v1/investigations/{case_id}?format=markdown"
        )

        assert report.status_code == 200
        public_report = report.json()
        endpoint = public_report["evidence"][0]["content_endpoint"]
        exact = client.get(endpoint)
        missing_scope = client.get(
            f"/api/v1/evidence/{public_report['evidence'][0]['evidence_id']}/content"
        )
        wrong_scope = client.get(
            f"/api/v1/evidence/{public_report['evidence'][0]['evidence_id']}/content",
            params={"version_id": "not-this-version"},
        )

    for payload in (
        report.text,
        archive.text,
        versions.text,
        events.text,
        markdown.text,
    ):
        assert marker not in payload
    assert "passage" not in public_report["evidence"][0]
    assert "source_url" not in public_report["evidence"][0]
    assert "exact_text" not in public_report["assertions"][0]
    assert "case_version_id" not in public_report["assertions"][0]
    assert "model_configuration" not in public_report
    assert "provider_diagnostics" not in public_report
    assert "trace" not in public_report
    assert "request_payload" not in archive.json()["items"][0]
    assert "report_payload" not in versions.json()["items"][0]
    assert exact.status_code == 200
    assert exact.json()["passage"] == marker
    assert missing_scope.status_code == 422
    assert wrong_scope.status_code == 404


def _inject_private_markers(
    repository: SQLiteCaseRepository, version_id: str, marker: str
) -> None:
    record = asyncio.run(repository.get_version(version_id))
    assert record.report_payload is not None
    report = json.loads(json.dumps(record.report_payload))
    report["assessment"]["summary"] = marker
    report["claims"][0]["text"] = marker
    report["evidence"][0]["passage"] = marker
    report["evidence"][0]["source_url"] = f"https://example.invalid/{marker}"
    report["assertions"][0]["exact_text"] = marker
    report["assertions"][0]["case_version_id"] = marker
    report["hypotheses"] = [
        {
            "hypothesis_id": "H1",
            "rank": 1,
            "status": "LEADING",
            "driver_label": "ISSUER_EVENT",
            "statement": marker,
            "supporting_evidence_ids": [report["evidence"][0]["evidence_id"]],
        }
    ]
    report["validation_results"] = [
        {
            "validation_id": "V1",
            "kind": "PRIVATE_VALIDATION",
            "status": "PASS",
            "summary": marker,
        }
    ]
    report["model_configuration"] = {"private": marker}
    report["provider_diagnostics"][0]["provenance"] = {"private": marker}
    report["ledger"][0]["model_configuration"] = {"private": marker}
    report["ledger"][0]["validation_summary"] = marker
    report["trace"] = [{"node": marker, "status": marker}]
    report["parent_case_id"] = marker
    request = {**record.request_payload, "untrusted_request_payload": marker}

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "UPDATE evidence_records SET passage = ? WHERE version_id = ?",
            (marker, version_id),
        )
        connection.execute(
            "UPDATE case_versions SET request_json = ?, report_json = ? WHERE version_id = ?",
            (
                repository._serialize_case_payload(request),
                repository._serialize_case_payload(report),
                version_id,
            ),
        )
        connection.commit()
