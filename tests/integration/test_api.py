from pathlib import Path
from time import sleep

import pytest
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


def test_default_app_routes_recorded_mode_without_live_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'default.db'}"
    )
    app = create_app()
    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        ).json()
        payload: dict[str, object] = {}
        for _ in range(40):
            payload = client.get(
                f"/api/v1/investigations/{accepted['case_id']}"
            ).json()
            if payload["status"] == "COMPLETED":
                break
            sleep(0.01)

    assert payload["outcome"] == "EXPLAINED"
