from datetime import date
from pathlib import Path

import httpx

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
