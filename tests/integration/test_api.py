from time import sleep

from fastapi.testclient import TestClient

from asx_investigator.api.app import create_app
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway


def test_api_creates_and_returns_a_recorded_investigation() -> None:
    app = create_app(InvestigationService(RecordedToolGateway.default()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        )
        assert response.status_code == 202
        case_id = response.json()["case_id"]

        for _ in range(20):
            result = client.get(f"/api/v1/investigations/{case_id}")
            if result.json()["status"] != "RUNNING":
                break
            sleep(0.01)

    assert result.status_code == 200
    assert result.json()["status"] == "COMPLETED"
    assert result.json()["assessment"]["primary_claim_id"] == "C1"


def test_api_renders_a_cited_markdown_report() -> None:
    app = create_app(InvestigationService(RecordedToolGateway.default()))
    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        )
        case_id = accepted.json()["case_id"]
        for _ in range(20):
            response = client.get(f"/api/v1/investigations/{case_id}")
            if response.json()["status"] != "RUNNING":
                break
            sleep(0.01)
        markdown = client.get(f"/api/v1/investigations/{case_id}?format=markdown")

    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "# BHP investigation" in markdown.text
    assert "[E1]" in markdown.text


def test_api_rejects_invalid_ticker() -> None:
    app = create_app(InvestigationService(RecordedToolGateway.default()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP.AX!", "trade_date": "2026-08-20", "mode": "RECORDED"},
        )

    assert response.status_code == 422
