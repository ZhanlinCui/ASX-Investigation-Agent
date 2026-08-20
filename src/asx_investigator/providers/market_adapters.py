from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx

from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus


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

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = client

    async def get_daily_bars(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[DailyBar]]:
        retrieved_at = datetime.now(UTC)
        symbol = f"{ticker.upper()}.AU"
        try:
            result = await self.client.get(
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
        except httpx.HTTPError:
            return self._failure(retrieved_at, "NETWORK_ERROR")
        if result.status_code >= 400:
            return self._failure(
                retrieved_at,
                f"HTTP_{result.status_code}",
                _failure_status(result.status_code),
            )
        try:
            rows = result.json()
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
                retrieved_at, "SCHEMA_INVALID", ProviderStatus.PERMANENT_FAILURE
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
        )

    def _failure(
        self,
        retrieved_at: datetime,
        error_code: str,
        status: ProviderStatus = ProviderStatus.RETRYABLE_FAILURE,
    ) -> ProviderOutcome[list[DailyBar]]:
        return ProviderOutcome[list[DailyBar]](
            status=status,
            provider=self.name,
            retrieved_at=retrieved_at,
            coverage="NONE",
            error_code=error_code,
            source_version="eod-v1",
        )


class MarketstackProvider:
    name = "Marketstack"

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = client

    async def get_daily_bars(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[DailyBar]]:
        retrieved_at = datetime.now(UTC)
        try:
            result = await self.client.get(
                "https://api.marketstack.com/v2/eod",
                params={
                    "access_key": self.api_key,
                    "symbols": f"{ticker.upper()}.XASX",
                    "date_from": (trade_date - timedelta(days=120)).isoformat(),
                    "date_to": trade_date.isoformat(),
                    "limit": 100,
                },
            )
        except httpx.HTTPError:
            return self._failure(retrieved_at, "NETWORK_ERROR")
        if result.status_code >= 400:
            return self._failure(
                retrieved_at,
                f"HTTP_{result.status_code}",
                _failure_status(result.status_code),
            )
        try:
            rows = result.json()["data"]
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
                retrieved_at, "SCHEMA_INVALID", ProviderStatus.PERMANENT_FAILURE
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
        )

    def _failure(
        self,
        retrieved_at: datetime,
        error_code: str,
        status: ProviderStatus = ProviderStatus.RETRYABLE_FAILURE,
    ) -> ProviderOutcome[list[DailyBar]]:
        return ProviderOutcome[list[DailyBar]](
            status=status,
            provider=self.name,
            retrieved_at=retrieved_at,
            coverage="NONE",
            error_code=error_code,
            source_version="marketstack-v2",
        )
