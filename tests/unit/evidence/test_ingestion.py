from pathlib import Path

import httpx
import pytest

from asx_investigator.evidence.ingestion import (
    MAX_SOURCE_BYTES,
    SourceIngestor,
    SourceRejected,
    validate_public_url,
)
from asx_investigator.storage.artifacts import ArtifactStore


class _MockConnector:
    """Deterministic test transport; production peer checks are covered separately."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get(
        self, url: httpx.URL, allowed_addresses: set[str]
    ) -> httpx.Response:
        request = self.client.build_request("GET", url)
        return await self.client.send(request, stream=True, follow_redirects=False)


def test_url_policy_rejects_private_and_non_http_targets() -> None:
    with pytest.raises(SourceRejected):
        validate_public_url("http://127.0.0.1/report", ["127.0.0.1"])
    with pytest.raises(SourceRejected):
        validate_public_url("http://localhost/report", ["127.0.0.1"])
    with pytest.raises(SourceRejected):
        validate_public_url("file:///tmp/report.pdf", [])


async def test_fetch_freezes_allowed_public_content(tmp_path: Path) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content=b"issuer guidance",
            )
        )
    )

    async def public_resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    ingestor = SourceIngestor(
        ArtifactStore(tmp_path), _MockConnector(client), resolver=public_resolver
    )
    source = await ingestor.fetch("https://issuer.example/report")

    assert source.size_bytes == len(b"issuer guidance")
    assert source.mime_type == "text/plain"
    assert ingestor.artifacts.get(source.artifact_id) == b"issuer guidance"


async def test_fetch_rejects_oversized_content_length(tmp_path: Path) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={
                    "content-type": "application/pdf",
                    "content-length": str(MAX_SOURCE_BYTES + 1),
                },
                content=b"small body with dishonest length",
            )
        )
    )

    async def public_resolver(host: str) -> list[str]:
        return ["93.184.216.34"]

    ingestor = SourceIngestor(
        ArtifactStore(tmp_path), _MockConnector(client), resolver=public_resolver
    )

    with pytest.raises(SourceRejected, match="20 MB"):
        await ingestor.fetch("https://issuer.example/report.pdf")


async def test_fetch_rejects_unsupported_mime_and_redirect_to_private_host(
    tmp_path: Path,
) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.host == "issuer.example":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"png")

    async def resolver(host: str) -> list[str]:
        return ["127.0.0.1"] if host == "127.0.0.1" else ["93.184.216.34"]

    ingestor = SourceIngestor(
        ArtifactStore(tmp_path),
        _MockConnector(httpx.AsyncClient(transport=httpx.MockTransport(responder))),
        resolver=resolver,
    )

    with pytest.raises(SourceRejected, match="Private and reserved"):
        await ingestor.fetch("https://issuer.example/report")
