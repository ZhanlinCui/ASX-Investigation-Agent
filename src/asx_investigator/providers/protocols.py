from __future__ import annotations

from datetime import date
from typing import Protocol

from asx_investigator.domain.models import EvidenceItem, InstrumentIdentity
from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.market import MarketDataResult


class InvestigationTools(Protocol):
    """The bounded, auditable data surface available to an investigation."""

    async def resolve_instrument(self, ticker: str) -> InstrumentIdentity: ...

    async def get_daily_bars(self, ticker: str, trade_date: date) -> list[DailyBar]: ...

    async def get_market_data(self, ticker: str, trade_date: date) -> MarketDataResult: ...

    async def get_benchmark_return(self, trade_date: date) -> float | None: ...

    async def get_evidence(self, ticker: str, trade_date: date) -> list[EvidenceItem]: ...

    async def disclosure_coverage_complete(self, ticker: str, trade_date: date) -> bool: ...
