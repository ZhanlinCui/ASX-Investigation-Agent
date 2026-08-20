from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from asx_investigator.evidence import ingestion
from asx_investigator.evidence.ingestion import SourceIngestor, SourceRejected
from asx_investigator.storage.artifacts import ArtifactStore


class _RouteConnector:
    def __init__(
        self,
        responder: Callable[[httpx.URL], httpx.Response],
    ) -> None:
        self.responder = responder
        self.calls: list[tuple[str, set[str]]] = []

    async def get(
        self, url: httpx.URL, allowed_addresses: set[str]
    ) -> httpx.Response:
        self.calls.append((str(url), allowed_addresses))
        response = self.responder(url)
        response.request = httpx.Request("GET", url)
        return response


class _PeerStream:
    def __init__(self, peer_address: str | None) -> None:
        self.peer_address = peer_address

    def get_extra_info(self, key: str):
        if key == "server_addr" and self.peer_address is not None:
            return (self.peer_address, 443)
        return None


async def test_redirect_target_is_resolved_and_revalidated(tmp_path: Path) -> None:
    resolved_hosts: list[str] = []

    async def resolver(host: str) -> list[str]:
        resolved_hosts.append(host)
        return ["127.0.0.1"] if host == "127.0.0.1" else ["93.184.216.34"]

    connector = _RouteConnector(
        lambda url: httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/x"},
            request=httpx.Request("GET", url),
        )
    )
    ingestor_instance = SourceIngestor(
        ArtifactStore(tmp_path / "artifacts"), connector, resolver=resolver
    )

    with pytest.raises(SourceRejected, match="Private and reserved"):
        await ingestor_instance.fetch("https://public.example/start")

    assert resolved_hosts == ["public.example", "127.0.0.1"]
    assert [url for url, _ in connector.calls] == ["https://public.example/start"]


async def test_final_redirect_url_is_bound_to_the_artifact_reference(
    tmp_path: Path,
) -> None:
    routes = {
        "https://public.example/start": httpx.Response(
            302, headers={"location": "https://filings.example/notice.txt"}
        ),
        "https://filings.example/notice.txt": httpx.Response(
            200, headers={"content-type": "text/plain"}, content=b"Official notice"
        ),
    }

    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    connector = _RouteConnector(lambda url: routes[str(url)])
    ingestor_instance = SourceIngestor(
        ArtifactStore(tmp_path / "artifacts"), connector, resolver=resolver
    )

    frozen = await ingestor_instance.fetch("https://public.example/start")

    assert frozen.source_url == "https://filings.example/notice.txt"
    assert frozen.artifact.locator == "https://filings.example/notice.txt"
    assert ingestor_instance.artifacts.get(frozen.artifact.artifact_id) == b"Official notice"


async def test_invalid_scheme_is_rejected_before_resolution_or_connection(
    tmp_path: Path,
) -> None:
    async def resolver(host: str) -> list[str]:
        raise AssertionError("invalid URL must not be resolved")

    connector = _RouteConnector(lambda url: httpx.Response(200))
    ingestor_instance = SourceIngestor(
        ArtifactStore(tmp_path / "artifacts"), connector, resolver=resolver
    )

    with pytest.raises(SourceRejected, match="Only public HTTP and HTTPS"):
        await ingestor_instance.fetch("file:///tmp/notice.txt")

    assert connector.calls == []


async def test_resolution_failure_is_a_source_rejection(tmp_path: Path) -> None:
    async def resolver(host: str) -> list[str]:
        raise OSError("resolver unavailable")

    connector = _RouteConnector(lambda url: httpx.Response(200))
    ingestor_instance = SourceIngestor(
        ArtifactStore(tmp_path / "artifacts"), connector, resolver=resolver
    )

    with pytest.raises(SourceRejected, match="could not be resolved"):
        await ingestor_instance.fetch("https://missing.example/notice.txt")

    assert connector.calls == []


async def test_production_connector_rejects_peer_mismatch() -> None:
    connector_type = getattr(ingestion, "HttpxPublicAddressConnector")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content=b"must not be admitted",
                extensions={"network_stream": _PeerStream("93.184.216.35")},
            )
        )
    )
    connector = connector_type(client=client)

    with pytest.raises(SourceRejected, match="peer address"):
        await connector.get(httpx.URL("https://public.example/x"), {"93.184.216.34"})

    await client.aclose()


async def test_production_connector_rejects_absent_peer_address() -> None:
    connector_type = getattr(ingestion, "HttpxPublicAddressConnector")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content=b"must not be admitted",
            )
        )
    )
    connector = connector_type(client=client)

    with pytest.raises(SourceRejected, match="peer address was unavailable"):
        await connector.get(httpx.URL("https://public.example/x"), {"93.184.216.34"})

    await client.aclose()


async def test_production_connector_disables_environment_proxies() -> None:
    connector_type = getattr(ingestion, "HttpxPublicAddressConnector")
    connector = connector_type()

    assert connector.client._trust_env is False

    await connector.aclose()
