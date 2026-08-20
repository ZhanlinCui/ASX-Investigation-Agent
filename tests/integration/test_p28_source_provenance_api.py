from __future__ import annotations

import sqlite3
from pathlib import Path
from time import sleep

from fastapi.testclient import TestClient

from asx_investigator.api.app import create_app
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.storage.artifacts import ArtifactStore
from asx_investigator.storage.repository import SQLiteCaseRepository
from tests.unit.test_p28_live_artifacts import (
    _ArtifactGateway,
    _UnavailableArtifactGateway,
)


def test_source_api_returns_hash_but_never_raw_body(tmp_path: Path) -> None:
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    app = create_app(
        InvestigationService(RecordedToolGateway.default()), repository=repository
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sources/upload",
            data={
                "title": "Official notice",
                "published_at": "2026-08-20T08:00:00+10:00",
                "is_official": "true",
            },
            files={"file": ("notice.txt", b"Official notice body", "text/plain")},
        )

    assert response.status_code == 201
    body = response.json()
    assert len(body["artifact_id"]) == 64
    assert body["artifact_id"].isalnum()
    assert "Official notice body" not in body.values()


def test_app_uses_one_artifact_store_for_live_tools_and_sources(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    app = create_app(repository=repository)

    with TestClient(app):
        live_tools = app.state.case_manager.service.tools
        assert live_tools.artifacts is app.state.artifact_store
        assert app.state.source_ingestor.artifacts is app.state.artifact_store


def test_provider_artifact_id_is_persisted_with_diagnostics(tmp_path: Path) -> None:
    artifacts = ArtifactStore(tmp_path / "artifacts")
    gateway = _ArtifactGateway(artifacts)
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    app = create_app(InvestigationService(gateway), repository=repository)

    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={
                "ticker": "BHP",
                "trade_date": "2026-08-20",
                "mode": "RECORDED",
            },
        ).json()
        for _ in range(50):
            report = client.get(
                f"/api/v1/investigations/{accepted['case_id']}"
            ).json()
            if report["status"] == "COMPLETED":
                break
            sleep(0.01)

    with sqlite3.connect(repository.database_path) as connection:
        rows = connection.execute(
            "SELECT artifact_id FROM provider_calls ORDER BY provider_call_id"
        ).fetchall()

    assert rows
    assert {row[0] for row in rows} == {gateway.reference.artifact_id}


def test_failed_provider_artifact_ids_are_persisted(tmp_path: Path) -> None:
    gateway = _UnavailableArtifactGateway(ArtifactStore(tmp_path / "artifacts"))
    repository = SQLiteCaseRepository(tmp_path / "cases.db")
    app = create_app(InvestigationService(gateway), repository=repository)

    with TestClient(app) as client:
        accepted = client.post(
            "/api/v1/investigations",
            json={
                "ticker": "BHP",
                "trade_date": "2026-08-20",
                "mode": "RECORDED",
            },
        ).json()
        for _ in range(50):
            report = client.get(
                f"/api/v1/investigations/{accepted['case_id']}"
            ).json()
            if report["status"] == "COMPLETED":
                break
            sleep(0.01)

    with sqlite3.connect(repository.database_path) as connection:
        rows = connection.execute(
            "SELECT artifact_id FROM provider_calls ORDER BY provider_call_id"
        ).fetchall()

    assert {row[0] for row in rows} == {
        item.artifact.artifact_id
        for item in gateway.outcomes
        if item.artifact is not None
    }
