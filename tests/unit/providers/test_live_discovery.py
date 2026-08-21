from datetime import date
from pathlib import Path

import httpx

from asx_investigator.investigation.planning import DriverLane, RetrievalTask
from asx_investigator.providers.live import LiveToolGateway
from asx_investigator.settings import Settings
from asx_investigator.storage.artifacts import ArtifactStore


async def test_tavily_results_remain_discovery_only_even_for_investor_urls(
    tmp_path: Path,
) -> None:
    payload = {
        "results": [
            {
                "url": "https://investors.issuer.example/announcement",
                "title": "Guidance update",
                "raw_content": "Guidance increased.",
                "published_date": "2026-08-20T08:00:00+10:00",
            }
        ]
    }
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )
    gateway = LiveToolGateway(
        Settings(tavily_api_key="secret"),
        client,
        artifacts=ArtifactStore(tmp_path),
    )

    evidence = await gateway.get_evidence("BHP", date(2026, 8, 20))

    assert evidence[0].role == "CONTEMPORANEOUS_REACTION"
    assert evidence[0].authority == "DISCOVERY_ONLY"


async def test_targeted_retrieval_uses_exact_gap_query_once(tmp_path: Path) -> None:
    requests: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    gateway = LiveToolGateway(
        Settings(tavily_api_key="secret"),
        httpx.AsyncClient(transport=httpx.MockTransport(responder)),
        artifacts=ArtifactStore(tmp_path),
    )

    result = await gateway.targeted_retrieve(
        "BHP",
        date(2026, 8, 20),
        "BHP production guidance 2026",
        "Check issuer guidance",
    )

    assert result == []
    assert len(requests) == 1
    assert "BHP production guidance 2026" in requests[0].content.decode()


async def test_planned_discovery_uses_only_the_sealed_lane_query_and_result_limit(
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    gateway = LiveToolGateway(
        Settings(tavily_api_key="secret"),
        httpx.AsyncClient(transport=httpx.MockTransport(responder)),
        artifacts=ArtifactStore(tmp_path),
    )
    task = RetrievalTask(
        task_id="R1",
        lane=DriverLane.INDEX_REBALANCE,
        tool="DISCOVER",
        query="BHP ASX index rebalance inclusion deletion 2026-08-20",
        purpose="Discover official index rebalance candidates.",
        max_results=2,
        max_document_bytes=120_000,
    )

    assert await gateway.execute_retrieval_task("BHP", date(2026, 8, 20), task) == []
    payload = requests[0].content.decode()
    assert task.query in payload
    assert '"max_results":2' in payload


async def test_planned_discovery_keeps_candidate_and_adds_only_frozen_primary_promotion(
    tmp_path: Path,
) -> None:
    class _Acquirer:
        async def promote(self, candidate, session, *, max_document_bytes):
            del session, max_document_bytes
            return candidate.model_copy(
                update={
                    "evidence_id": f"{candidate.evidence_id}-P",
                    "authority": "PRIMARY_ISSUER",
                    "role": "CAUSAL_INPUT",
                }
            )

    payload = {
        "results": [
            {
                "url": "https://investors.issuer.example/announcement",
                "title": "Guidance update",
                "raw_content": "Discovery content",
                "published_date": "2026-08-20T08:00:00+10:00",
            }
        ]
    }
    gateway = LiveToolGateway(
        Settings(tavily_api_key="secret"),
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
        ),
        artifacts=ArtifactStore(tmp_path),
        official_acquirer=_Acquirer(),
    )
    task = RetrievalTask(
        task_id="R1",
        lane=DriverLane.ISSUER_DISCLOSURE,
        tool="DISCOVER",
        query="BHP ASX announcement 2026-08-20",
        purpose="Discover contemporaneous issuer disclosure candidates.",
        max_results=2,
        max_document_bytes=120_000,
    )

    evidence = await gateway.execute_retrieval_task("BHP", date(2026, 8, 20), task)

    assert [(item.authority, item.role) for item in evidence] == [
        ("DISCOVERY_ONLY", "CONTEMPORANEOUS_REACTION"),
        ("PRIMARY_ISSUER", "CAUSAL_INPUT"),
    ]
