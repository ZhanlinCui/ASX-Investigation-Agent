from time import sleep

from fastapi.testclient import TestClient

from asx_investigator.api.app import create_app
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.storage.repository import SQLiteCaseRepository


def test_report_exposes_checkpoint_lineage_without_artifact_content(tmp_path) -> None:
    app = create_app(
        InvestigationService(RecordedToolGateway.default()),
        repository=SQLiteCaseRepository(tmp_path / "cases.db"),
    )
    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        ).json()
        for _ in range(50):
            body = client.get(f"/api/v1/investigations/{accepted['case_id']}").json()
            if body["status"] == "COMPLETED":
                break
            sleep(0.01)

    assert body["checkpoint_lineage"][-1]["stage"] == "deterministic_validation"
    assert body["artifact_hashes"] == []
    assert "input_artifact_hashes" not in body["checkpoint_lineage"][0]
    assert "provider_diagnostics" not in body
