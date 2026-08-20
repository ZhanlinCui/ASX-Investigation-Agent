from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable

import httpx
from pydantic import BaseModel

from asx_investigator.storage.artifacts import ArtifactStore

MAX_SOURCE_BYTES = 20 * 1024 * 1024
ALLOWED_MIME_TYPES = {"application/pdf", "text/html", "text/plain"}


class SourceRejected(ValueError):
    """Raised when a user source violates the acquisition policy."""


class FrozenSource(BaseModel):
    artifact_id: str
    source_url: str | None = None
    mime_type: str
    size_bytes: int
    sha256: str


def validate_public_url(url: str, resolved_addresses: list[str]) -> httpx.URL:
    parsed = httpx.URL(url)
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise SourceRejected("Only public HTTP and HTTPS sources are allowed")
    if parsed.host.lower() == "localhost":
        raise SourceRejected("Private and local source hosts are not allowed")
    for value in resolved_addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise SourceRejected("Private and reserved source addresses are not allowed")
    if not resolved_addresses:
        raise SourceRejected("The source host did not resolve to a public address")
    return parsed


async def _resolve_host(host: str) -> list[str]:
    records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    return sorted({str(record[4][0]) for record in records})


class SourceIngestor:
    def __init__(
        self,
        artifacts: ArtifactStore,
        client: httpx.AsyncClient,
        *,
        resolver: Callable[[str], Awaitable[list[str]]] = _resolve_host,
    ) -> None:
        self.artifacts = artifacts
        self.client = client
        self.resolver = resolver

    def upload(self, content: bytes, mime_type: str) -> FrozenSource:
        normalized_mime = mime_type.split(";", 1)[0].strip().lower()
        self._validate_content(content, normalized_mime)
        artifact = self.artifacts.put(content, normalized_mime)
        return FrozenSource(
            artifact_id=artifact.artifact_id,
            mime_type=artifact.mime_type,
            size_bytes=artifact.size_bytes,
            sha256=artifact.sha256,
        )

    async def fetch(self, url: str) -> FrozenSource:
        current = url
        for _ in range(4):
            parsed = httpx.URL(current)
            addresses = await self.resolver(parsed.host or "")
            validate_public_url(current, addresses)
            async with self.client.stream(
                "GET", current, follow_redirects=False
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise SourceRejected("Redirect response did not include a location")
                    current = str(response.url.join(location))
                    continue
                response.raise_for_status()
                declared_size = int(response.headers.get("content-length", "0") or 0)
                if declared_size > MAX_SOURCE_BYTES:
                    raise SourceRejected("Sources must not exceed 20 MB")
                mime_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].lower()
                )
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_SOURCE_BYTES:
                        raise SourceRejected("Sources must not exceed 20 MB")
            frozen_content = bytes(content)
            self._validate_content(frozen_content, mime_type)
            artifact = self.artifacts.put(frozen_content, mime_type)
            return FrozenSource(
                artifact_id=artifact.artifact_id,
                source_url=current,
                mime_type=artifact.mime_type,
                size_bytes=artifact.size_bytes,
                sha256=artifact.sha256,
            )
        raise SourceRejected("Source exceeded the three-redirect limit")

    @staticmethod
    def _validate_content(content: bytes, mime_type: str) -> None:
        if mime_type not in ALLOWED_MIME_TYPES:
            raise SourceRejected(f"Unsupported source MIME type: {mime_type or 'missing'}")
        if len(content) > MAX_SOURCE_BYTES:
            raise SourceRejected("Sources must not exceed 20 MB")
        if not content:
            raise SourceRejected("Source content is empty")
