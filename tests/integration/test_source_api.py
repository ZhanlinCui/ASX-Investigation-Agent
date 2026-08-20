from time import sleep

from fastapi.testclient import TestClient

from asx_investigator.api.app import create_app
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway


def test_uploaded_text_is_frozen_added_to_case_and_opened_as_exact_passage() -> None:
    app = create_app(InvestigationService(RecordedToolGateway.default()))
    with TestClient(app) as client:
        uploaded = client.post(
            "/api/v1/sources/upload",
            data={
                "title": "User supplied operating update",
                "published_at": "2026-08-20T08:00:00+10:00",
                "is_official": "true",
            },
            files={"file": ("update.txt", b"Production guidance increased.", "text/plain")},
        )
        assert uploaded.status_code == 201
        source = uploaded.json()

        accepted = client.post(
            "/api/v1/investigations",
            json={
                "ticker": "BHP",
                "trade_date": "2026-08-20",
                "mode": "RECORDED",
                "source_ids": [source["source_id"]],
            },
        ).json()
        payload: dict[str, object] = {}
        for _ in range(40):
            payload = client.get(
                f"/api/v1/investigations/{accepted['case_id']}"
            ).json()
            if payload["status"] == "COMPLETED":
                break
            sleep(0.01)

        uploaded_evidence = next(
            item for item in payload["evidence"] if item["title"] == source["title"]
        )
        passage = client.get(
            f"/api/v1/evidence/{uploaded_evidence['evidence_id']}/content"
        )

    assert passage.status_code == 200
    assert passage.json()["passage"] == "Production guidance increased."
    assert passage.json()["locator"] == "block:1"


def test_source_fetch_rejects_private_url_before_network_request() -> None:
    app = create_app(InvestigationService(RecordedToolGateway.default()))
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sources/fetch",
            json={
                "url": "http://127.0.0.1/private",
                "title": "Private",
                "published_at": "2026-08-20T08:00:00+10:00",
            },
        )

    assert response.status_code == 422


def test_refinement_inherits_attached_sources_unless_explicitly_replaced() -> None:
    app = create_app(InvestigationService(RecordedToolGateway.default()))
    with TestClient(app) as client:
        source = client.post(
            "/api/v1/sources/upload",
            data={
                "title": "Inherited source",
                "published_at": "2026-08-20T08:00:00+10:00",
                "is_official": "true",
            },
            files={"file": ("source.txt", b"Material operating update.", "text/plain")},
        ).json()
        accepted = client.post(
            "/api/v1/investigations",
            json={
                "ticker": "BHP",
                "trade_date": "2026-08-20",
                "mode": "RECORDED",
                "source_ids": [source["source_id"]],
            },
        ).json()

        refined = client.post(
            f"/api/v1/investigations/{accepted['case_id']}/versions",
            json={"primary_only": True},
        )
        versions = client.get(
            f"/api/v1/investigations/{accepted['case_id']}/versions"
        ).json()["items"]

    assert refined.status_code == 202
    assert versions[-1]["request_payload"]["source_ids"] == [source["source_id"]]
