from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx
from pydantic import BaseModel

from asx_investigator.storage.artifacts import ArtifactReference, ArtifactStore

MAX_SOURCE_BYTES = 20 * 1024 * 1024
ALLOWED_MIME_TYPES = {"application/pdf", "text/html", "text/plain"}


class SourceRejected(ValueError):
    """Raised when a user source violates the acquisition policy."""


class FrozenSource(BaseModel):
    artifact: ArtifactReference
    source_url: str | None = None

    @property
    def artifact_id(self) -> str:
        return self.artifact.artifact_id

    @property
    def mime_type(self) -> str:
        return self.artifact.mime_type

    @property
    def size_bytes(self) -> int:
        return self.artifact.size_bytes

    @property
    def sha256(self) -> str:
        return self.artifact.sha256


class PublicAddressConnector(Protocol):
    async def get(
        self, url: httpx.URL, allowed_addresses: set[str]
    ) -> httpx.Response: ...


def _normalize_public_addresses(resolved_addresses: list[str] | set[str]) -> set[str]:
    if not resolved_addresses:
        raise SourceRejected("The source host did not resolve to a public address")
    normalized: set[str] = set()
    for value in resolved_addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as error:
            raise SourceRejected("The source host returned an invalid address") from error
        if not address.is_global:
            raise SourceRejected("Private and reserved source addresses are not allowed")
        normalized.add(str(address))
    return normalized


def _parse_public_url(url: str | httpx.URL) -> httpx.URL:
    try:
        parsed = httpx.URL(url)
    except (httpx.InvalidURL, UnicodeError, ValueError) as error:
        raise SourceRejected("Only public HTTP and HTTPS sources are allowed") from error
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise SourceRejected("Only public HTTP and HTTPS sources are allowed")
    if parsed.host.lower() == "localhost":
        raise SourceRejected("Private and local source hosts are not allowed")
    return parsed


def validate_public_url(
    url: str | httpx.URL, resolved_addresses: list[str] | set[str]
) -> httpx.URL:
    parsed = _parse_public_url(url)
    _normalize_public_addresses(resolved_addresses)
    return parsed


async def _resolve_host(host: str) -> list[str]:
    records = await asyncio.to_thread(socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM)
    return sorted({str(record[4][0]) for record in records})


def _response_peer_address(response: httpx.Response) -> str | None:
    stream = response.extensions.get("network_stream")
    get_extra_info = getattr(stream, "get_extra_info", None)
    if get_extra_info is None:
        return None
    server_address = get_extra_info("server_addr")
    if isinstance(server_address, tuple) and server_address:
        return str(server_address[0])
    if isinstance(server_address, str):
        return server_address
    return None


class HttpxPublicAddressConnector:
    """HTTP transport that admits content only from the just-resolved public peer."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20,
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        )

    async def get(
        self, url: httpx.URL, allowed_addresses: set[str]
    ) -> httpx.Response:
        validated_addresses = _normalize_public_addresses(allowed_addresses)
        request = self.client.build_request("GET", url)
        response = await self.client.send(
            request,
            stream=True,
            follow_redirects=False,
        )
        peer_value = _response_peer_address(response)
        if peer_value is None:
            await response.aclose()
            raise SourceRejected("The response peer address was unavailable")
        try:
            peer = ipaddress.ip_address(peer_value)
        except ValueError as error:
            await response.aclose()
            raise SourceRejected("The response peer address was invalid") from error
        if not peer.is_global:
            await response.aclose()
            raise SourceRejected("The response peer address was private or reserved")
        if str(peer) not in validated_addresses:
            await response.aclose()
            raise SourceRejected(
                "The response peer address did not match the validated source addresses"
            )
        return response

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()


class SourceIngestor:
    def __init__(
        self,
        artifacts: ArtifactStore,
        connector: PublicAddressConnector,
        *,
        resolver: Callable[[str], Awaitable[list[str]]] = _resolve_host,
    ) -> None:
        self.artifacts = artifacts
        self.connector = connector
        self.resolver = resolver

    def upload(self, content: bytes, mime_type: str) -> FrozenSource:
        normalized_mime = mime_type.split(";", 1)[0].strip().lower()
        self._validate_content(content, normalized_mime)
        artifact = self.artifacts.put(content, normalized_mime)
        return FrozenSource(
            artifact=ArtifactReference.model_validate(artifact.model_dump()),
        )

    async def fetch(self, url: str) -> FrozenSource:
        current = url
        redirects = 0
        while True:
            candidate = _parse_public_url(current)
            try:
                addresses = set(await self.resolver(candidate.host or ""))
            except OSError as error:
                raise SourceRejected("The source host could not be resolved") from error
            parsed = validate_public_url(candidate, addresses)
            response = await self.connector.get(parsed, addresses)
            try:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise SourceRejected("Redirect response did not include a location")
                    if redirects >= 3:
                        raise SourceRejected("Source exceeded the three-redirect limit")
                    current = str(response.url.join(location))
                    redirects += 1
                    continue
                response.raise_for_status()
                try:
                    declared_size = int(response.headers.get("content-length", "0") or 0)
                except ValueError as error:
                    raise SourceRejected("Source content length was invalid") from error
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
            finally:
                await response.aclose()
            frozen_content = bytes(content)
            self._validate_content(frozen_content, mime_type)
            artifact = self.artifacts.put(frozen_content, mime_type)
            reference = ArtifactReference.model_validate(
                {**artifact.model_dump(), "locator": str(parsed)}
            )
            return FrozenSource(
                artifact=reference,
                source_url=current,
            )

    @staticmethod
    def _validate_content(content: bytes, mime_type: str) -> None:
        if mime_type not in ALLOWED_MIME_TYPES:
            raise SourceRejected(f"Unsupported source MIME type: {mime_type or 'missing'}")
        if len(content) > MAX_SOURCE_BYTES:
            raise SourceRejected("Sources must not exceed 20 MB")
        if not content:
            raise SourceRejected("Source content is empty")
