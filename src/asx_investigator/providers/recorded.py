from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from asx_investigator.domain.models import EvidenceItem, EvidenceRole, InstrumentIdentity
from asx_investigator.market.forensics import DailyBar
from asx_investigator.providers.market import CorporateAction, MarketDataResult
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus

SYDNEY = ZoneInfo("Australia/Sydney")


@dataclass(frozen=True)
class RecordedToolGateway:
    """Small deterministic fixture set used for development, demos and regression tests.

    Recorded cases are deliberately labelled as such at the API boundary. They are
    not a substitute for a licensed historical market-data archive.
    """

    @classmethod
    def default(cls) -> RecordedToolGateway:
        return cls()

    async def resolve_instrument(self, ticker: str) -> InstrumentIdentity:
        if ticker.upper() != "BHP":
            raise LookupError(f"No recorded instrument for {ticker.upper()}")
        return InstrumentIdentity(
            asx_code="BHP",
            company_name="BHP Group Limited",
            sector="Materials",
        )

    async def get_daily_bars(self, ticker: str, trade_date: date) -> list[DailyBar]:
        if ticker.upper() != "BHP" or trade_date != date(2026, 8, 20):
            raise LookupError("No recorded price history for this case")
        start = trade_date - timedelta(days=60)
        bars = [
            DailyBar(
                trade_date=start + timedelta(days=index),
                open=10.0,
                high=10.2,
                low=9.9,
                close=10.0,
                adjusted_close=10.0,
                volume=100_000,
            )
            for index in range(60)
        ]
        bars.append(
            DailyBar(
                trade_date=trade_date,
                open=10.5,
                high=11.2,
                low=10.4,
                close=11.0,
                adjusted_close=11.0,
                volume=500_000,
            )
        )
        return bars

    async def get_benchmark_return(self, trade_date: date) -> float | None:
        return 1.0 if trade_date == date(2026, 8, 20) else None

    async def get_market_data(self, ticker: str, trade_date: date) -> MarketDataResult:
        bars = await self.get_daily_bars(ticker, trade_date)
        return MarketDataResult(
            bars=bars,
            selected_provider="RECORDED_FIXTURE",
            outcomes=[
                ProviderOutcome[list[DailyBar]](
                    status=ProviderStatus.SUCCESS,
                    provider="RECORDED_FIXTURE",
                    retrieved_at=datetime(2026, 8, 20, 16, 30, tzinfo=SYDNEY),
                    coverage="COMPLETE",
                    data=bars,
                    source_version="recorded-v1",
                )
            ],
        )

    async def get_corporate_actions(
        self, ticker: str, trade_date: date
    ) -> ProviderOutcome[list[CorporateAction]]:
        return ProviderOutcome[list[CorporateAction]](
            status=ProviderStatus.SUCCESS,
            provider="RECORDED_CORPORATE_ACTION_FIXTURE",
            retrieved_at=datetime(2026, 8, 20, 16, 30, tzinfo=SYDNEY),
            coverage="COMPLETE",
            data=[],
            source_version="recorded-v1",
        )

    async def get_evidence(self, ticker: str, trade_date: date) -> list[EvidenceItem]:
        if ticker.upper() != "BHP" or trade_date != date(2026, 8, 20):
            return []
        published_at = datetime(2026, 8, 20, 8, 30, tzinfo=SYDNEY)
        return [
            EvidenceItem(
                evidence_id="E1",
                source_name="BHP Investor Relations",
                source_url="https://example.test/bhp/fy26-guidance-update",
                published_at=published_at,
                retrieved_at=datetime(2026, 8, 20, 16, 30, tzinfo=SYDNEY),
                role=EvidenceRole.CAUSAL_INPUT,
                authority="PRIMARY_ISSUER",
                title="FY26 guidance update",
                passage="BHP raised its FY26 production guidance before ASX trading opened.",
                content_hash="recorded-bhp-guidance-v1",
                locator="Recorded fixture: announcement summary",
            )
        ]

    async def disclosure_coverage_complete(self, ticker: str, trade_date: date) -> bool:
        return ticker.upper() == "BHP" and trade_date == date(2026, 8, 20)

    async def targeted_retrieve(
        self,
        ticker: str,
        trade_date: date,
        query: str,
        purpose: str,
    ) -> list[EvidenceItem]:
        return []
