from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx

from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.market import CorporateAction
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


class EODHDCorporateActionsProvider:
    name = "EODHD_ASX_CORPORATE_ACTIONS"

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self.api_key = api_key
        self.client = client

    async def get_corporate_actions(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[CorporateAction]]:
        retrieved_at = datetime.now(UTC)
        try:
            response = await self.client.get(
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
        except httpx.HTTPError:
            return self._failure(retrieved_at, "NETWORK_ERROR")
        if response.status_code >= 400:
            return self._failure(
                retrieved_at,
                f"HTTP_{response.status_code}",
                _failure_status(response.status_code),
            )
        try:
            rows = response.json()["data"]
            actions = [self._parse_action(row) for row in rows]
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return self._failure(
                retrieved_at, "SCHEMA_INVALID", ProviderStatus.PERMANENT_FAILURE
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
    ) -> ProviderOutcome[list[CorporateAction]]:
        return ProviderOutcome[list[CorporateAction]](
            status=status,
            provider=self.name,
            retrieved_at=retrieved_at,
            coverage="NONE",
            error_code=error_code,
            source_version="asx-corporate-actions-beta-v1",
        )
