from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.capture import capture_provider_payload
from asx_investigator.providers.market import CorporateAction
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus
from asx_investigator.storage.artifacts import ArtifactReference, ArtifactStore

MAX_PROVIDER_RESPONSE_BYTES = 20 * 1024 * 1024


class ProviderResponseTooLarge(httpx.RequestError):
    """Raised before an unbounded provider response can enter the application."""

    def __init__(
        self,
        artifact: ArtifactReference,
        *,
        request: httpx.Request,
    ) -> None:
        super().__init__("Provider response exceeded 20 MB", request=request)
        self.artifact = artifact


class ProviderResponseReadError(httpx.RequestError):
    """Carries a frozen partial response when the provider stream fails."""

    def __init__(
        self,
        artifact: ArtifactReference,
        *,
        request: httpx.Request,
    ) -> None:
        super().__init__("Provider response stream failed", request=request)
        self.artifact = artifact


@dataclass(frozen=True)
class CapturedJsonResponse:
    status_code: int
    payload: object | None
    artifact: ArtifactReference | None


async def request_captured_json(
    client: httpx.AsyncClient,
    artifacts: ArtifactStore,
    method: str,
    url: str,
    **request_kwargs: object,
) -> CapturedJsonResponse:
    """Freeze bounded JSON response content before any provider-specific parsing."""

    async with client.stream(
        method, url, follow_redirects=False, **request_kwargs
    ) as response:
        content = bytearray()
        try:
            async for chunk in response.aiter_bytes():
                if len(content) + len(chunk) > MAX_PROVIDER_RESPONSE_BYTES:
                    artifact = capture_provider_payload(
                        artifacts,
                        {
                            "error_code": "RESPONSE_TOO_LARGE",
                            "status_code": response.status_code,
                        },
                        "application/json",
                    )
                    raise ProviderResponseTooLarge(artifact, request=response.request)
                content.extend(chunk)
        except ProviderResponseTooLarge:
            raise
        except httpx.HTTPError as error:
            if not content:
                artifact = capture_provider_payload(
                    artifacts,
                    {
                        "body_empty": True,
                        "error_code": "NETWORK_ERROR",
                        "status_code": response.status_code,
                    },
                    "application/json",
                )
                raise ProviderResponseReadError(
                    artifact, request=response.request
                ) from error
            artifact = capture_provider_payload(
                artifacts,
                {
                    "body": bytes(content).decode("utf-8", errors="replace"),
                    "error_code": "NETWORK_ERROR",
                    "status_code": response.status_code,
                },
                "application/json",
            )
            raise ProviderResponseReadError(
                artifact, request=response.request
            ) from error
        status_code = response.status_code

    if not content:
        artifact = capture_provider_payload(
            artifacts,
            {"body_empty": True, "status_code": status_code},
            "application/json",
        )
        return CapturedJsonResponse(
            status_code=status_code,
            payload=None,
            artifact=artifact,
        )

    try:
        decoded: object = json.loads(bytes(content))
    except (UnicodeDecodeError, json.JSONDecodeError):
        frozen_payload: object = {
            "body": bytes(content).decode("utf-8", errors="replace"),
            "status_code": status_code,
        }
        parsed_payload = None
    else:
        frozen_payload = (
            {"payload": decoded, "status_code": status_code}
            if not 200 <= status_code < 300
            else decoded
        )
        parsed_payload = decoded

    artifact = capture_provider_payload(artifacts, frozen_payload, "application/json")
    captured = json.loads(artifacts.get(artifact.artifact_id))
    if 200 <= status_code < 300 and parsed_payload is not None:
        parsed_payload = captured
    elif parsed_payload is not None:
        parsed_payload = captured["payload"]
    return CapturedJsonResponse(
        status_code=status_code,
        payload=parsed_payload,
        artifact=artifact,
    )


def _failure_status(status_code: int) -> ProviderStatus:
    return (
        ProviderStatus.RETRYABLE_FAILURE
        if status_code == 429 or status_code >= 500
        else ProviderStatus.PERMANENT_FAILURE
    )


def _coverage_status(bars: list[DailyBar], trade_date: date) -> tuple[ProviderStatus, str]:
    complete = len(bars) >= 41 and bars[-1].trade_date == trade_date
    return (
        (ProviderStatus.SUCCESS, "COMPLETE")
        if complete
        else (ProviderStatus.PARTIAL, "PARTIAL")
    )


class EODHDProvider:
    name = "EODHD"

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient,
        artifacts: ArtifactStore,
    ) -> None:
        self.api_key = api_key
        self.client = client
        self.artifacts = artifacts

    async def get_daily_bars(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[DailyBar]]:
        retrieved_at = datetime.now(UTC)
        symbol = f"{ticker.upper()}.AU"
        try:
            result = await request_captured_json(
                self.client,
                self.artifacts,
                "GET",
                f"https://eodhd.com/api/eod/{symbol}",
                params={
                    "api_token": self.api_key,
                    "fmt": "json",
                    "period": "d",
                    "order": "a",
                    "from": (trade_date - timedelta(days=120)).isoformat(),
                    "to": trade_date.isoformat(),
                },
            )
        except ProviderResponseTooLarge as error:
            return self._failure(
                retrieved_at,
                "RESPONSE_TOO_LARGE",
                ProviderStatus.PERMANENT_FAILURE,
                artifact=error.artifact,
            )
        except ProviderResponseReadError as error:
            return self._failure(
                retrieved_at,
                "NETWORK_ERROR",
                artifact=error.artifact,
            )
        except httpx.HTTPError:
            return self._failure(retrieved_at, "NETWORK_ERROR")
        if not 200 <= result.status_code < 300:
            return self._failure(
                retrieved_at,
                f"HTTP_{result.status_code}",
                _failure_status(result.status_code),
                artifact=result.artifact,
            )
        try:
            rows = result.payload
            bars = sorted(
                [
                    DailyBar(
                        trade_date=date.fromisoformat(row["date"]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        adjusted_close=float(row["adjusted_close"]),
                        volume=int(row["volume"]),
                    )
                    for row in rows
                ],
                key=lambda item: item.trade_date,
            )
        except (KeyError, TypeError, ValueError):
            return self._failure(
                retrieved_at,
                "SCHEMA_INVALID",
                ProviderStatus.PERMANENT_FAILURE,
                artifact=result.artifact,
            )
        if not bars:
            return ProviderOutcome[list[DailyBar]](
                status=ProviderStatus.EMPTY,
                provider=self.name,
                retrieved_at=retrieved_at,
                coverage="COMPLETE",
                data=[],
                provenance={"symbol": symbol, "endpoint": "eod"},
                source_version="eod-v1",
                artifact=result.artifact,
            )
        status, coverage = _coverage_status(bars, trade_date)
        return ProviderOutcome[list[DailyBar]](
            status=status,
            provider=self.name,
            retrieved_at=retrieved_at,
            coverage=coverage,
            data=bars,
            provenance={"symbol": symbol, "endpoint": "eod"},
            source_version="eod-v1",
            artifact=result.artifact,
        )

    def _failure(
        self,
        retrieved_at: datetime,
        error_code: str,
        status: ProviderStatus = ProviderStatus.RETRYABLE_FAILURE,
        *,
        artifact: ArtifactReference | None = None,
    ) -> ProviderOutcome[list[DailyBar]]:
        return ProviderOutcome[list[DailyBar]](
            status=status,
            provider=self.name,
            retrieved_at=retrieved_at,
            coverage="NONE",
            error_code=error_code,
            source_version="eod-v1",
            artifact=artifact,
        )


class MarketstackProvider:
    name = "Marketstack"

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient,
        artifacts: ArtifactStore,
    ) -> None:
        self.api_key = api_key
        self.client = client
        self.artifacts = artifacts

    async def get_daily_bars(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[DailyBar]]:
        retrieved_at = datetime.now(UTC)
        try:
            result = await request_captured_json(
                self.client,
                self.artifacts,
                "GET",
                "https://api.marketstack.com/v2/eod",
                params={
                    "access_key": self.api_key,
                    "symbols": f"{ticker.upper()}.XASX",
                    "date_from": (trade_date - timedelta(days=120)).isoformat(),
                    "date_to": trade_date.isoformat(),
                    "limit": 100,
                },
            )
        except ProviderResponseTooLarge as error:
            return self._failure(
                retrieved_at,
                "RESPONSE_TOO_LARGE",
                ProviderStatus.PERMANENT_FAILURE,
                artifact=error.artifact,
            )
        except ProviderResponseReadError as error:
            return self._failure(
                retrieved_at,
                "NETWORK_ERROR",
                artifact=error.artifact,
            )
        except httpx.HTTPError:
            return self._failure(retrieved_at, "NETWORK_ERROR")
        if not 200 <= result.status_code < 300:
            return self._failure(
                retrieved_at,
                f"HTTP_{result.status_code}",
                _failure_status(result.status_code),
                artifact=result.artifact,
            )
        try:
            if not isinstance(result.payload, dict):
                raise TypeError("Marketstack payload must be an object")
            rows = result.payload["data"]
            bars = sorted(
                [
                    DailyBar(
                        trade_date=date.fromisoformat(row["date"][:10]),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        adjusted_close=float(row.get("adj_close") or row["close"]),
                        volume=int(row["volume"]),
                    )
                    for row in rows
                ],
                key=lambda item: item.trade_date,
            )
        except (KeyError, TypeError, ValueError):
            return self._failure(
                retrieved_at,
                "SCHEMA_INVALID",
                ProviderStatus.PERMANENT_FAILURE,
                artifact=result.artifact,
            )
        provenance = {"exchange": "XASX", "endpoint": "v2/eod"}
        if not bars:
            return ProviderOutcome[list[DailyBar]](
                status=ProviderStatus.EMPTY,
                provider=self.name,
                retrieved_at=retrieved_at,
                coverage="COMPLETE",
                data=[],
                provenance=provenance,
                source_version="marketstack-v2",
                artifact=result.artifact,
            )
        status, coverage = _coverage_status(bars, trade_date)
        return ProviderOutcome[list[DailyBar]](
            status=status,
            provider=self.name,
            retrieved_at=retrieved_at,
            coverage=coverage,
            data=bars,
            provenance=provenance,
            source_version="marketstack-v2",
            artifact=result.artifact,
        )

    def _failure(
        self,
        retrieved_at: datetime,
        error_code: str,
        status: ProviderStatus = ProviderStatus.RETRYABLE_FAILURE,
        *,
        artifact: ArtifactReference | None = None,
    ) -> ProviderOutcome[list[DailyBar]]:
        return ProviderOutcome[list[DailyBar]](
            status=status,
            provider=self.name,
            retrieved_at=retrieved_at,
            coverage="NONE",
            error_code=error_code,
            source_version="marketstack-v2",
            artifact=artifact,
        )


class EODHDCorporateActionsProvider:
    name = "EODHD_ASX_CORPORATE_ACTIONS"

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient,
        artifacts: ArtifactStore,
    ) -> None:
        self.api_key = api_key
        self.client = client
        self.artifacts = artifacts

    async def get_corporate_actions(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[CorporateAction]]:
        retrieved_at = datetime.now(UTC)
        try:
            response = await request_captured_json(
                self.client,
                self.artifacts,
                "GET",
                "https://eodhd.com/api/asx-corporate-actions",
                params={
                    "api_token": self.api_key,
                    "symbol": f"{ticker.upper()}.AU",
                    "date_from": trade_date.isoformat(),
                    "date_to": trade_date.isoformat(),
                    "page[limit]": 100,
                    "fmt": "json",
                },
            )
        except ProviderResponseTooLarge as error:
            return self._failure(
                retrieved_at,
                "RESPONSE_TOO_LARGE",
                ProviderStatus.PERMANENT_FAILURE,
                artifact=error.artifact,
            )
        except ProviderResponseReadError as error:
            return self._failure(
                retrieved_at,
                "NETWORK_ERROR",
                artifact=error.artifact,
            )
        except httpx.HTTPError:
            return self._failure(retrieved_at, "NETWORK_ERROR")
        if not 200 <= response.status_code < 300:
            return self._failure(
                retrieved_at,
                f"HTTP_{response.status_code}",
                _failure_status(response.status_code),
                artifact=response.artifact,
            )
        try:
            if not isinstance(response.payload, dict):
                raise TypeError("Corporate action payload must be an object")
            rows = response.payload["data"]
            actions = [self._parse_action(row) for row in rows]
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return self._failure(
                retrieved_at,
                "SCHEMA_INVALID",
                ProviderStatus.PERMANENT_FAILURE,
                artifact=response.artifact,
            )
        provenance = {
            "symbol": f"{ticker.upper()}.AU",
            "endpoint": "asx-corporate-actions",
            "upstream": "ASX ReferencePoint E34",
        }
        return ProviderOutcome[list[CorporateAction]](
            status=ProviderStatus.SUCCESS if actions else ProviderStatus.EMPTY,
            provider=self.name,
            retrieved_at=retrieved_at,
            coverage="COMPLETE",
            data=actions,
            provenance=provenance,
            source_version="asx-corporate-actions-beta-v1",
            artifact=response.artifact,
        )

    @staticmethod
    def _parse_action(row: dict[str, object]) -> CorporateAction:
        extra = row.get("_asx_extra")
        asx_extra = extra if isinstance(extra, dict) else {}
        effective = asx_extra.get("effective_date") or row.get("date")
        if not isinstance(effective, str):
            raise ValueError("Corporate action has no effective date")
        split = row.get("split")
        adjustment_factor: float | None = None
        if isinstance(split, str) and ":" in split:
            numerator, denominator = split.split(":", 1)
            adjustment_factor = float(numerator) / float(denominator)
        value = row.get("value")
        action_type = "SPLIT" if split else str(row.get("type") or "CORPORATE_ACTION").upper()
        source_id = asx_extra.get("corporate_action_id")
        return CorporateAction(
            action_type=action_type,
            effective_date=date.fromisoformat(effective),
            adjustment_factor=adjustment_factor,
            cash_amount_aud=float(value) if isinstance(value, int | float) else None,
            source_id=str(source_id or f"{row.get('code', 'ASX')}:{effective}:{action_type}"),
        )

    def _failure(
        self,
        retrieved_at: datetime,
        error_code: str,
        status: ProviderStatus = ProviderStatus.RETRYABLE_FAILURE,
        *,
        artifact: ArtifactReference | None = None,
    ) -> ProviderOutcome[list[CorporateAction]]:
        return ProviderOutcome[list[CorporateAction]](
            status=status,
            provider=self.name,
            retrieved_at=retrieved_at,
            coverage="NONE",
            error_code=error_code,
            source_version="asx-corporate-actions-beta-v1",
            artifact=artifact,
        )
