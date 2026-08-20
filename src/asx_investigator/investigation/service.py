from __future__ import annotations

from datetime import date
from uuid import uuid4

from asx_investigator.agent.gemini import NarrativeGenerator
from asx_investigator.confidence.scoring import ConfidenceFeatures, score_confidence
from asx_investigator.domain.models import (
    Claim,
    ClaimType,
    EvidenceItem,
    EvidenceRole,
    InvestigationReport,
    InvestigationStatus,
    PrimaryAssessment,
    TradingSession,
)
from asx_investigator.evidence.validation import validate_claims
from asx_investigator.market.forensics import calculate_market_move
from asx_investigator.market.sessions import classify_event, resolve_session
from asx_investigator.providers.protocols import InvestigationTools


class InvestigationService:
    """Run a bounded investigation and refuse unsupported causal conclusions."""

    def __init__(
        self, tools: InvestigationTools, narrator: NarrativeGenerator | None = None
    ) -> None:
        self.tools = tools
        self.narrator = narrator

    async def investigate(
        self, ticker: str, trade_date: str | date, mode: str = "LIVE"
    ) -> InvestigationReport:
        normalized_ticker = ticker.upper().strip()
        requested_date = (
            date.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date
        )
        session = resolve_session(requested_date)
        trace = [{"node": "resolve_session", "status": "COMPLETED"}]
        instrument = await self.tools.resolve_instrument(normalized_ticker)
        trace.append({"node": "resolve_instrument", "status": "COMPLETED"})

        if not session.is_trading_day:
            return InvestigationReport(
                case_id=str(uuid4()),
                run_id=str(uuid4()),
                status=InvestigationStatus.PARTIAL,
                ticker=normalized_ticker,
                trade_date=requested_date,
                timezone_label=session.timezone_label,
                instrument=instrument,
                assessment=PrimaryAssessment(
                    summary="The requested date was not an ASX trading session."
                ),
                confidence=score_confidence(
                    ConfidenceFeatures(0, 0, 0, 0, 0, 0, has_primary_evidence=False)
                ),
                coverage_status="NOT_A_TRADING_DAY",
                trace=trace,
            )

        bars = await self.tools.get_daily_bars(normalized_ticker, requested_date)
        benchmark_return = await self.tools.get_benchmark_return(requested_date)
        market_move = calculate_market_move(bars, benchmark_return)
        trace.append({"node": "market_forensics", "status": "COMPLETED"})

        raw_evidence = await self.tools.get_evidence(normalized_ticker, requested_date)
        evidence = self._eligible_evidence(raw_evidence, session)
        trace.append({"node": "retrieve_and_time_evidence", "status": "COMPLETED"})
        causal = [item for item in evidence if item.role == EvidenceRole.CAUSAL_INPUT]
        coverage_complete = await self.tools.disclosure_coverage_complete(
            normalized_ticker, requested_date
        )

        if causal:
            leading = causal[0]
            generated = (
                await self.narrator.explain(normalized_ticker, market_move, causal)
                if self.narrator
                else None
            )
            if generated and generated.primary_evidence_id in {item.evidence_id for item in causal}:
                leading = next(
                    item for item in causal if item.evidence_id == generated.primary_evidence_id
                )
                claim_text = generated.explanation
            else:
                claim_text = (
                    f"{leading.title} is the leading explanation for {normalized_ticker}'s "
                    f"{market_move.close_return_pct:+.1f}% close-to-close move."
                )
            claim = Claim(
                claim_id="C1",
                claim_type=ClaimType.CAUSE,
                text=claim_text,
                supporting_evidence_ids=[leading.evidence_id],
            )
            primary = PrimaryAssessment(
                primary_claim_id=claim.claim_id,
                summary=claim.text,
            )
        else:
            claim = Claim(
                claim_id="C1",
                claim_type=ClaimType.UNRESOLVED,
                text=(
                    "No contemporaneous primary evidence was found that can safely explain "
                    "the move."
                ),
            )
            primary = PrimaryAssessment(primary_claim_id=None, summary=claim.text)

        confidence = score_confidence(
            ConfidenceFeatures(
                source_authority=1.0 if causal else 0.2,
                temporal_eligibility=1.0 if causal else 0.0,
                market_signature_fit=0.9 if causal and market_move.is_unusual else 0.4,
                quantitative_consistency=0.9 if market_move.is_unusual else 0.5,
                independent_corroboration=0.5 if causal else 0.0,
                coverage_completeness=1.0 if coverage_complete else 0.4,
                has_primary_evidence=bool(causal),
                disclosure_coverage_complete=coverage_complete,
            )
        )
        claim.confidence = confidence.score
        validate_claims([claim], {item.evidence_id: item for item in evidence})
        trace.append({"node": "validate_claims", "status": "COMPLETED"})
        return InvestigationReport(
            case_id=str(uuid4()),
            run_id=str(uuid4()),
            status=InvestigationStatus.COMPLETED if causal else InvestigationStatus.PARTIAL,
            ticker=normalized_ticker,
            trade_date=requested_date,
            timezone_label=session.timezone_label,
            instrument=instrument,
            market_move=market_move,
            assessment=primary,
            claims=[claim],
            evidence=evidence,
            confidence=confidence,
            coverage_status="COMPLETE" if coverage_complete else "PARTIAL_DISCLOSURE_COVERAGE",
            trace=trace,
        )

    @staticmethod
    def _eligible_evidence(
        evidence: list[EvidenceItem], session: TradingSession
    ) -> list[EvidenceItem]:
        # Evidence that post-dates the relevant session is retained only as context,
        # never silently promoted into a same-day causal claim.
        eligible: list[EvidenceItem] = []
        for item in evidence:
            timing = classify_event(item.published_at, session)
            if item.role == EvidenceRole.CAUSAL_INPUT and not timing.eligible_same_day_cause:
                item = item.model_copy(update={"role": EvidenceRole.RETROSPECTIVE_CONTEXT})
            eligible.append(item)
        return eligible
