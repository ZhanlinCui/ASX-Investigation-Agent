from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx

from asx_investigator.domain.models import EvidenceItem, EvidenceRole, InstrumentIdentity
from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.errors import DataProviderUnavailable
from asx_investigator.providers.market import (
    CorporateAction,
    MarketDataReconciler,
    MarketDataResult,
    MarketDataUnavailable,
    within_live_window,
)
from asx_investigator.providers.market_adapters import (
    EODHDCorporateActionsProvider,
    EODHDProvider,
    MarketstackProvider,
    ProviderResponseReadError,
    ProviderResponseTooLarge,
    request_captured_json,
)
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus
from asx_investigator.settings import Settings
from asx_investigator.storage.artifacts import ArtifactReference, ArtifactStore

SYDNEY = ZoneInfo("Australia/Sydney")


class LiveToolGateway:
    """Live tool adapter with explicit source roles and no silent synthetic fallback."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        *,
        artifacts: ArtifactStore,
    ) -> None:
        self.settings = settings
        self.artifacts = artifacts
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=20, trust_env=False)

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _require_eodhd(self) -> str:
        if not self.settings.eodhd_api_key:
            raise DataProviderUnavailable("EODHD_API_KEY is required for live market data")
        return self.settings.eodhd_api_key

    async def resolve_instrument(self, ticker: str) -> InstrumentIdentity:
        instrument, _ = await self.resolve_eodhd_instrument(ticker)
        return instrument

    async def resolve_eodhd_instrument(
        self, ticker: str
    ) -> tuple[InstrumentIdentity, ProviderOutcome[InstrumentIdentity]]:
        # EODHD recognises ASX symbols with the .AU suffix. The issuer name is
        # reconciled against the price source rather than guessed by the model.
        token = self._require_eodhd()
        retrieved_at = datetime.now(UTC)
        symbol = f"{ticker.upper()}.AU"
        try:
            response = await request_captured_json(
                self.client,
                self.artifacts,
                "GET",
                f"https://eodhd.com/api/search/{ticker}",
                params={"api_token": token, "fmt": "json", "limit": 20},
            )
        except ProviderResponseTooLarge as error:
            self._raise_instrument_unavailable(
                retrieved_at,
                "RESPONSE_TOO_LARGE",
                ProviderStatus.PERMANENT_FAILURE,
                symbol=symbol,
                artifact=error.artifact,
            )
        except ProviderResponseReadError as error:
            self._raise_instrument_unavailable(
                retrieved_at,
                "NETWORK_ERROR",
                ProviderStatus.RETRYABLE_FAILURE,
                symbol=symbol,
                artifact=error.artifact,
            )
        except httpx.HTTPError:
            self._raise_instrument_unavailable(
                retrieved_at,
                "NETWORK_ERROR",
                ProviderStatus.RETRYABLE_FAILURE,
                symbol=symbol,
            )
        if not 200 <= response.status_code < 300:
            self._raise_instrument_unavailable(
                retrieved_at,
                f"HTTP_{response.status_code}",
                (
                    ProviderStatus.RETRYABLE_FAILURE
                    if response.status_code == 429 or response.status_code >= 500
                    else ProviderStatus.PERMANENT_FAILURE
                ),
                symbol=symbol,
                artifact=response.artifact,
            )
        matches = response.payload
        if not isinstance(matches, list):
            self._raise_instrument_unavailable(
                retrieved_at,
                "SCHEMA_INVALID",
                ProviderStatus.PERMANENT_FAILURE,
                symbol=symbol,
                artifact=response.artifact,
            )
        if not all(isinstance(item, dict) for item in matches):
            self._raise_instrument_unavailable(
                retrieved_at,
                "SCHEMA_INVALID",
                ProviderStatus.PERMANENT_FAILURE,
                symbol=symbol,
                artifact=response.artifact,
            )
        if not all(
            isinstance(item.get("Code"), str) and isinstance(item.get("Exchange"), str)
            for item in matches
        ):
            self._raise_instrument_unavailable(
                retrieved_at,
                "SCHEMA_INVALID",
                ProviderStatus.PERMANENT_FAILURE,
                symbol=symbol,
                artifact=response.artifact,
            )
        match = next(
            (
                item
                for item in matches
                if item.get("Code", "").upper() == ticker.upper()
                and item.get("Exchange", "").upper() in {"AU", "ASX"}
            ),
            None,
        )
        if match is None:
            raise LookupError(f"Could not resolve {ticker} as an ASX-listed equity")
        company_name = match.get("Name", ticker.upper())
        sector = match.get("Sector")
        if not isinstance(company_name, str) or not isinstance(sector, (str, type(None))):
            self._raise_instrument_unavailable(
                retrieved_at,
                "SCHEMA_INVALID",
                ProviderStatus.PERMANENT_FAILURE,
                symbol=symbol,
                artifact=response.artifact,
            )
        instrument = InstrumentIdentity(
            asx_code=ticker.upper(),
            company_name=company_name,
            sector=sector,
        )
        return instrument, ProviderOutcome(
            status=ProviderStatus.SUCCESS,
            provider="EODHD_SEARCH",
            retrieved_at=retrieved_at,
            coverage="COMPLETE",
            data=instrument,
            provenance={"symbol": symbol, "endpoint": "search"},
            source_version="search-v1",
            artifact=response.artifact,
        )

    @staticmethod
    def _raise_instrument_unavailable(
        retrieved_at: datetime,
        error_code: str,
        status: ProviderStatus,
        *,
        symbol: str,
        artifact: ArtifactReference | None = None,
    ) -> None:
        outcome = ProviderOutcome[InstrumentIdentity](
            status=status,
            provider="EODHD_SEARCH",
            retrieved_at=retrieved_at,
            coverage="NONE",
            provenance={"symbol": symbol, "endpoint": "search"},
            error_code=error_code,
            source_version="search-v1",
            artifact=artifact,
        )
        raise DataProviderUnavailable(
            f"Instrument provider unavailable: {error_code}", outcomes=[outcome]
        )

    async def get_daily_bars(self, ticker: str, trade_date: date) -> list[DailyBar]:
        return (await self.get_market_data(ticker, trade_date)).bars

    async def get_market_data(self, ticker: str, trade_date: date) -> MarketDataResult:
        if not within_live_window(trade_date, today=date.today()):
            raise DataProviderUnavailable(
                "The requested date is outside the trailing 12-month live window"
            )
        primary = EODHDProvider(self._require_eodhd(), self.client, self.artifacts)
        fallback = (
            MarketstackProvider(
                self.settings.marketstack_api_key,
                self.client,
                self.artifacts,
            )
            if self.settings.marketstack_api_key
            else None
        )
        try:
            return await MarketDataReconciler(primary, fallback).acquire(ticker, trade_date)
        except MarketDataUnavailable as error:
            codes = ", ".join(item.error_code or str(item.status) for item in error.outcomes)
            raise DataProviderUnavailable(
                f"Market data unavailable: {codes}",
                outcomes=error.outcomes,
            ) from error

    async def get_eodhd_market_data(
        self, ticker: str, trade_date: date
    ) -> MarketDataResult:
        """Acquire EODHD only for bounded provider verification.

        Normal investigations still use the governed fallback/conflict policy in
        :meth:`get_market_data`. The credential smoke instead proves the primary
        provider in isolation, so it must not trigger a Marketstack request.
        """

        if not within_live_window(trade_date, today=date.today()):
            raise DataProviderUnavailable(
                "The requested date is outside the trailing 12-month live window"
            )
        primary = await EODHDProvider(
            self._require_eodhd(), self.client, self.artifacts
        ).get_daily_bars(ticker, trade_date)
        if primary.status in {ProviderStatus.SUCCESS, ProviderStatus.PARTIAL} and primary.data:
            return MarketDataResult(
                bars=primary.data,
                selected_provider=primary.provider,
                outcomes=[primary],
            )
        raise DataProviderUnavailable(
            f"Market data unavailable: {primary.error_code or primary.status}",
            outcomes=[primary],
        )

    async def get_benchmark_return(self, trade_date: date) -> float | None:
        # Return None if no benchmark entitlement is configured: downstream
        # confidence reports the gap rather than treating an index as zero.
        return None

    async def get_corporate_actions(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[CorporateAction]]:
        return await EODHDCorporateActionsProvider(
            self._require_eodhd(), self.client, self.artifacts
        ).get_corporate_actions(ticker, trade_date)

    async def get_evidence(self, ticker: str, trade_date: date) -> list[EvidenceItem]:
        return await self._discover(
            f"{ticker} ASX announcement {trade_date.isoformat()}",
            trade_date,
            id_prefix="D",
        )

    async def targeted_retrieve(
        self,
        ticker: str,
        trade_date: date,
        query: str,
        purpose: str,
    ) -> list[EvidenceItem]:
        return await self._discover(
            f"{query} {ticker} ASX",
            trade_date,
            id_prefix="T",
        )

    async def _discover(
        self,
        query: str,
        trade_date: date,
        *,
        id_prefix: str,
    ) -> list[EvidenceItem]:
        if not self.settings.tavily_api_key:
            return []
        response = await request_captured_json(
            self.client,
            self.artifacts,
            "POST",
            "https://api.tavily.com/search",
            json={
                "api_key": self.settings.tavily_api_key,
                "query": query,
                "topic": "news",
                "search_depth": "advanced",
                "max_results": 8,
                "include_raw_content": "markdown",
            },
        )
        if not 200 <= response.status_code < 300:
            raise DataProviderUnavailable(
                f"Discovery provider unavailable: HTTP_{response.status_code}"
            )
        payload = response.payload
        if not isinstance(payload, dict):
            raise DataProviderUnavailable("Discovery provider returned an invalid schema")
        items: list[EvidenceItem] = []
        for index, row in enumerate(payload.get("results", []), start=1):
            url = row.get("url", "")
            host = (httpx.URL(url).host or "").lower()
            if host == "asx.com.au" or host.endswith(".asx.com.au"):
                continue
            title = row.get("title", "Untitled result")
            content = row.get("raw_content") or row.get("content") or ""
            published = self._parse_published_at(row.get("published_date"), trade_date)
            items.append(
                EvidenceItem(
                    evidence_id=f"{id_prefix}{index}",
                    source_name=host or "Web discovery",
                    source_url=url,
                    published_at=published,
                    retrieved_at=datetime.now(SYDNEY),
                    role=EvidenceRole.CONTEMPORANEOUS_REACTION,
                    authority="DISCOVERY_ONLY",
                    title=title,
                    passage=content[:4000],
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                    locator="Tavily discovery result",
                )
            )
        return items

    async def disclosure_coverage_complete(self, ticker: str, trade_date: date) -> bool:
        # Search is discovery only; an official announcement feed/PDF acquisition
        # is required before live disclosure coverage can be labelled complete.
        return False

    @staticmethod
    def _parse_published_at(value: str | None, fallback: date) -> datetime:
        if value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(SYDNEY)
            except ValueError:
                pass
        return datetime.combine(fallback, datetime.min.time(), tzinfo=SYDNEY)
