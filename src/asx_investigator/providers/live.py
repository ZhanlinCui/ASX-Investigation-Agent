from __future__ import annotations

import hashlib
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from asx_investigator.domain.models import EvidenceItem, EvidenceRole, InstrumentIdentity
from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.market import (
    MarketDataReconciler,
    MarketDataResult,
    MarketDataUnavailable,
    within_live_window,
)
from asx_investigator.providers.market_adapters import EODHDProvider, MarketstackProvider
from asx_investigator.settings import Settings

SYDNEY = ZoneInfo("Australia/Sydney")


class DataProviderUnavailable(RuntimeError):
    """Raised when the configured provider cannot safely answer a tool call."""


class LiveToolGateway:
    """Live tool adapter with explicit source roles and no silent synthetic fallback."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=20)

    def _require_eodhd(self) -> str:
        if not self.settings.eodhd_api_key:
            raise DataProviderUnavailable("EODHD_API_KEY is required for live market data")
        return self.settings.eodhd_api_key

    async def resolve_instrument(self, ticker: str) -> InstrumentIdentity:
        # EODHD recognises ASX symbols with the .AU suffix. The issuer name is
        # reconciled against the price source rather than guessed by the model.
        token = self._require_eodhd()
        response = await self.client.get(
            f"https://eodhd.com/api/search/{ticker}",
            params={"api_token": token, "fmt": "json", "limit": 20},
        )
        response.raise_for_status()
        matches = response.json()
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
        return InstrumentIdentity(
            asx_code=ticker.upper(),
            company_name=match.get("Name", ticker.upper()),
            sector=match.get("Sector"),
        )

    async def get_daily_bars(self, ticker: str, trade_date: date) -> list[DailyBar]:
        return (await self.get_market_data(ticker, trade_date)).bars

    async def get_market_data(self, ticker: str, trade_date: date) -> MarketDataResult:
        if not within_live_window(trade_date, today=date.today()):
            raise DataProviderUnavailable(
                "The requested date is outside the trailing 12-month live window"
            )
        primary = EODHDProvider(self._require_eodhd(), self.client)
        fallback = (
            MarketstackProvider(self.settings.marketstack_api_key, self.client)
            if self.settings.marketstack_api_key
            else None
        )
        try:
            return await MarketDataReconciler(primary, fallback).acquire(ticker, trade_date)
        except MarketDataUnavailable as error:
            codes = ", ".join(item.error_code or str(item.status) for item in error.outcomes)
            raise DataProviderUnavailable(f"Market data unavailable: {codes}") from error

    async def get_benchmark_return(self, trade_date: date) -> float | None:
        # Return None if no benchmark entitlement is configured: downstream
        # confidence reports the gap rather than treating an index as zero.
        return None

    async def get_evidence(self, ticker: str, trade_date: date) -> list[EvidenceItem]:
        if not self.settings.tavily_api_key:
            return []
        response = await self.client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.settings.tavily_api_key,
                "query": f"{ticker} ASX announcement {trade_date.isoformat()}",
                "topic": "news",
                "search_depth": "advanced",
                "max_results": 8,
                "include_raw_content": "markdown",
            },
        )
        response.raise_for_status()
        items: list[EvidenceItem] = []
        for index, row in enumerate(response.json().get("results", []), start=1):
            url = row.get("url", "")
            title = row.get("title", "Untitled result")
            content = row.get("raw_content") or row.get("content") or ""
            published = self._parse_published_at(row.get("published_date"), trade_date)
            # ASX pages are not scraped. A result is primary only when it is
            # recognisably hosted on an issuer investor-relations site.
            is_primary = "investor" in url.lower() or "investors" in url.lower()
            role = (
                EvidenceRole.CAUSAL_INPUT
                if is_primary
                else EvidenceRole.CONTEMPORANEOUS_REACTION
            )
            items.append(
                EvidenceItem(
                    evidence_id=f"W{index}",
                    source_name=(url.split("/")[2] if "/" in url else "Web result"),
                    source_url=url,
                    published_at=published,
                    retrieved_at=datetime.now(SYDNEY),
                    role=role,
                    authority="PRIMARY_ISSUER" if is_primary else "SECONDARY_MEDIA",
                    title=title,
                    passage=content[:4000],
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                    locator="Tavily result",
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
