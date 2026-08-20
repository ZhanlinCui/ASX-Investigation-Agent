from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from uuid import uuid4

from asx_investigator.agent.reasoning import (
    ChallengeResult,
    HypothesisBatch,
    HypothesisProposal,
    InvestigationReasoner,
    ReasoningUnavailable,
    ReasoningValidationError,
    ValidatedReasoning,
    validate_reasoning,
)
from asx_investigator.confidence.scoring import ConfidenceFeatures, score_confidence
from asx_investigator.domain.models import (
    Claim,
    ClaimType,
    CompletenessAssessment,
    CoverageGap,
    EvidenceItem,
    EvidenceRole,
    InvestigationOutcome,
    InvestigationReport,
    InvestigationStatus,
    PrimaryAssessment,
    TradingSession,
    ValidationResult,
    ValidationStatus,
)
from asx_investigator.evidence.context import EvidencePacket, build_evidence_packet
from asx_investigator.evidence.validation import validate_claims
from asx_investigator.market.forensics import calculate_market_move
from asx_investigator.market.sessions import classify_event, resolve_session
from asx_investigator.providers.errors import DataProviderUnavailable
from asx_investigator.providers.outcomes import ProviderStatus
from asx_investigator.providers.protocols import InvestigationTools

StageObserver = Callable[[str, str, dict[str, object]], Awaitable[None]]


class InvestigationService:
    """Evidence-first state machine whose model output is never directly publishable."""

    def __init__(
        self,
        tools: InvestigationTools,
        reasoner: InvestigationReasoner | None = None,
    ) -> None:
        self.tools = tools
        self.reasoner = reasoner

    async def investigate(
        self,
        ticker: str,
        trade_date: str | date,
        mode: str = "LIVE",
        on_stage: StageObserver | None = None,
    ) -> InvestigationReport:
        normalized_ticker = ticker.upper().strip()
        requested_date = (
            date.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date
        )
        trace: list[dict[str, str]] = []

        await self._stage(trace, on_stage, "resolve_instrument", "RUNNING")
        instrument = await self.tools.resolve_instrument(normalized_ticker)
        await self._stage(trace, on_stage, "resolve_instrument", "COMPLETED")

        await self._stage(trace, on_stage, "resolve_asx_session", "RUNNING")
        session = resolve_session(requested_date)
        await self._stage(trace, on_stage, "resolve_asx_session", "COMPLETED")
        if not session.is_trading_day:
            return self._non_trading_report(
                normalized_ticker, requested_date, session, instrument, trace
            )

        await self._stage(trace, on_stage, "acquire_market_data", "RUNNING")
        try:
            market_data = await self.tools.get_market_data(normalized_ticker, requested_date)
        except DataProviderUnavailable as error:
            await self._stage(trace, on_stage, "acquire_market_data", "INCOMPLETE")
            return self._incomplete_market_report(
                normalized_ticker,
                requested_date,
                session,
                instrument,
                str(error),
                trace,
            )
        benchmark_return = await self.tools.get_benchmark_return(requested_date)
        market_move = calculate_market_move(market_data.bars, benchmark_return)
        await self._stage(trace, on_stage, "acquire_market_data", "COMPLETED")

        await self._stage(trace, on_stage, "test_mechanical_explanations", "RUNNING")
        corporate_actions = await self.tools.get_corporate_actions(
            normalized_ticker, requested_date
        )
        corporate_action_coverage = corporate_actions.status in {
            ProviderStatus.SUCCESS,
            ProviderStatus.EMPTY,
        }
        validations = [
            ValidationResult(
                validation_id="V-MECHANICAL",
                kind="CORPORATE_ACTION_CHECK",
                status=(
                    ValidationStatus.PASS
                    if corporate_action_coverage
                    else ValidationStatus.NOT_AVAILABLE
                ),
                summary=(
                    f"The authoritative feed returned {len(corporate_actions.data or [])} "
                    "corporate actions for the session; price fields were not used to invent "
                    "missing events."
                    if corporate_action_coverage
                    else "The corporate-action feed was unavailable; no mechanical explanation "
                    "was inferred from price fields alone."
                ),
            )
        ]
        await self._stage(trace, on_stage, "test_mechanical_explanations", "COMPLETED")

        await self._stage(trace, on_stage, "discover_and_freeze_documents", "RUNNING")
        raw_evidence = await self.tools.get_evidence(normalized_ticker, requested_date)
        evidence = self._eligible_evidence(raw_evidence, session)
        await self._stage(trace, on_stage, "discover_and_freeze_documents", "COMPLETED")

        await self._stage(trace, on_stage, "extract_exact_passages", "RUNNING")
        await self._stage(trace, on_stage, "extract_exact_passages", "COMPLETED")
        coverage_complete = await self.tools.disclosure_coverage_complete(
            normalized_ticker, requested_date
        )
        coverage_gaps = [market_data.coverage_gap] if market_data.coverage_gap else []
        if not corporate_action_coverage:
            coverage_gaps.append(
                CoverageGap(
                    gap_id="CORPORATE_ACTIONS_UNAVAILABLE",
                    capability="corporate_actions",
                    provider=corporate_actions.provider,
                    reason=corporate_actions.error_code or str(corporate_actions.status),
                    impact=(
                        "A mechanical split, distribution or reconstruction cannot be ruled out."
                    ),
                    retryable=corporate_actions.status == ProviderStatus.RETRYABLE_FAILURE,
                )
            )
        if not coverage_complete:
            coverage_gaps.append(
                CoverageGap(
                    gap_id="DISCLOSURE_COVERAGE_PARTIAL",
                    capability="issuer_disclosures",
                    provider="issuer_ir",
                    reason="A complete point-in-time issuer disclosure archive was unavailable.",
                    impact="Causal confidence is capped and no-catalyst cannot be concluded.",
                )
            )

        await self._stage(trace, on_stage, "assemble_evidence_packet", "RUNNING")
        packet = build_evidence_packet(
            normalized_ticker,
            market_move,
            evidence,
            coverage_gaps,
            market_data.conflicts,
        )
        await self._stage(trace, on_stage, "assemble_evidence_packet", "COMPLETED")

        validated: ValidatedReasoning | None = None
        reasoning_error: str | None = None
        try:
            validated, evidence, packet = await self._reason(
                mode=mode,
                ticker=normalized_ticker,
                trade_date=requested_date,
                session=session,
                packet=packet,
                evidence=evidence,
                market_move=market_move,
                coverage_gaps=coverage_gaps,
                conflicts=market_data.conflicts,
                trace=trace,
                on_stage=on_stage,
            )
        except (ReasoningUnavailable, ReasoningValidationError) as error:
            reasoning_error = str(error)
            validations.append(
                ValidationResult(
                    validation_id="V-REASONING",
                    kind="MODEL_OUTPUT_VALIDATION",
                    status=ValidationStatus.FAIL,
                    summary=reasoning_error,
                )
            )
        if validated:
            validations.extend(validated.validations)

        causal = [item for item in evidence if item.role == EvidenceRole.CAUSAL_INPUT]
        selected = validated.leading if validated else None
        if selected:
            claim = Claim(
                claim_id="C1",
                claim_type=ClaimType.CAUSE,
                text=selected.statement,
                supporting_evidence_ids=selected.supporting_evidence_ids,
                contradicting_evidence_ids=selected.contradicting_evidence_ids,
            )
            outcome = InvestigationOutcome.EXPLAINED
            primary = PrimaryAssessment(primary_claim_id="C1", summary=claim.text)
        else:
            summary = (
                "No contemporaneous primary evidence was found after complete disclosure "
                "coverage checks."
                if not causal and coverage_complete
                else "The available evidence cannot support a validated causal explanation."
            )
            claim = Claim(claim_id="C1", claim_type=ClaimType.UNRESOLVED, text=summary)
            outcome = (
                InvestigationOutcome.NO_IDENTIFIABLE_CATALYST
                if not causal and coverage_complete and reasoning_error is None
                else InvestigationOutcome.INSUFFICIENT_EVIDENCE
            )
            primary = PrimaryAssessment(primary_claim_id=None, summary=summary)

        await self._stage(trace, on_stage, "confidence_and_abstention", "RUNNING")
        confidence = score_confidence(
            ConfidenceFeatures(
                source_authority=1.0 if selected else 0.2,
                temporal_eligibility=1.0 if selected else 0.0,
                market_signature_fit=0.9 if selected and market_move.is_unusual else 0.4,
                quantitative_consistency=0.9 if market_move.is_unusual else 0.5,
                independent_corroboration=(
                    0.7 if selected and len(selected.supporting_evidence_ids) > 1 else 0.0
                ),
                coverage_completeness=1.0 if coverage_complete else 0.4,
                alternative_strength=(
                    0.4 if validated and len(validated.hypotheses) > 1 else 0.0
                ),
                has_primary_evidence=bool(selected),
                disclosure_coverage_complete=coverage_complete,
                has_material_conflict=bool(market_data.conflicts),
            )
        )
        claim.confidence = confidence.score
        validate_claims([claim], {item.evidence_id: item for item in evidence})
        await self._stage(trace, on_stage, "confidence_and_abstention", "COMPLETED")

        missing = [gap.capability for gap in coverage_gaps]
        missing_capabilities = missing
        completeness_score = 1.0 if not missing_capabilities and not market_data.conflicts else 0.5
        return InvestigationReport(
            case_id=str(uuid4()),
            run_id=str(uuid4()),
            status=InvestigationStatus.COMPLETED,
            outcome=outcome,
            ticker=normalized_ticker,
            trade_date=requested_date,
            timezone_label=session.timezone_label,
            instrument=instrument,
            market_move=market_move,
            assessment=primary,
            claims=[claim],
            evidence=evidence,
            confidence=confidence,
            completeness=CompletenessAssessment(
                score=completeness_score,
                status="COMPLETE" if completeness_score == 1 else "PARTIAL",
                required_capabilities=[
                    "market_data",
                    "issuer_disclosures",
                    "corporate_actions",
                ],
                missing_capabilities=missing_capabilities,
            ),
            hypotheses=validated.hypotheses if validated else [],
            validation_results=validations,
            coverage_gaps=coverage_gaps,
            conflicts=market_data.conflicts,
            coverage_status="COMPLETE" if coverage_complete else "PARTIAL_DISCLOSURE_COVERAGE",
            model_configuration=(
                getattr(
                    self.reasoner,
                    "model_configuration",
                    {"provider": "INJECTED_REASONER", "structured_calls_max": "2"},
                )
                if self.reasoner
                else {"provider": "RECORDED_DETERMINISTIC", "structured_calls_max": "0"}
            ),
            trace=trace,
        )

    async def _reason(
        self,
        *,
        mode: str,
        ticker: str,
        trade_date: date,
        session: TradingSession,
        packet: EvidencePacket,
        evidence: list[EvidenceItem],
        market_move,
        coverage_gaps: list[CoverageGap],
        conflicts,
        trace: list[dict[str, str]],
        on_stage: StageObserver | None,
    ) -> tuple[ValidatedReasoning | None, list[EvidenceItem], EvidencePacket]:
        causal = [item for item in evidence if item.role == EvidenceRole.CAUSAL_INPUT]
        if self.reasoner is None:
            if mode.upper() != "RECORDED" or not causal:
                return None, evidence, packet
            batch = HypothesisBatch(
                hypotheses=[
                    HypothesisProposal(
                        hypothesis_id="H1",
                        rank=1,
                        statement=(
                            f"{causal[0].title} is the leading explanation for the recorded "
                            f"{ticker} move."
                        ),
                        expected_signature="Directionally consistent unusual price and volume.",
                        supporting_evidence_ids=[causal[0].evidence_id],
                    )
                ]
            )
            challenge = ChallengeResult(
                leading_hypothesis_id="H1",
                timing_leakage=False,
                unsupported_assumptions=[],
                summary="The recorded fixture contains no stronger admissible alternative.",
            )
            await self._stage(trace, on_stage, "deterministic_validation", "RUNNING")
            validated = validate_reasoning(batch, challenge, packet)
            await self._stage(trace, on_stage, "deterministic_validation", "COMPLETED")
            return validated, evidence, packet

        await self._stage(trace, on_stage, "generate_ranked_hypotheses", "RUNNING")
        batch = await self.reasoner.generate(packet)
        await self._stage(trace, on_stage, "generate_ranked_hypotheses", "COMPLETED")

        if batch.evidence_gap:
            retriever = getattr(self.tools, "targeted_retrieve", None)
            if retriever is not None:
                await self._stage(trace, on_stage, "targeted_retrieval", "RUNNING")
                retrieved = await retriever(
                    ticker,
                    trade_date,
                    batch.evidence_gap.query,
                    batch.evidence_gap.purpose,
                )
                known = {item.evidence_id for item in evidence}
                evidence.extend(
                    item
                    for item in self._eligible_evidence(retrieved, session)
                    if item.evidence_id not in known
                )
                packet = build_evidence_packet(
                    ticker, market_move, evidence, coverage_gaps, conflicts
                )
                await self._stage(trace, on_stage, "targeted_retrieval", "COMPLETED")

        await self._stage(trace, on_stage, "challenge_leading_hypothesis", "RUNNING")
        challenge = await self.reasoner.challenge(packet, batch)
        await self._stage(trace, on_stage, "challenge_leading_hypothesis", "COMPLETED")
        await self._stage(trace, on_stage, "deterministic_validation", "RUNNING")
        validated = validate_reasoning(batch, challenge, packet)
        await self._stage(trace, on_stage, "deterministic_validation", "COMPLETED")
        return validated, evidence, packet

    @staticmethod
    async def _stage(
        trace: list[dict[str, str]],
        observer: StageObserver | None,
        stage: str,
        status: str,
    ) -> None:
        trace.append({"node": stage, "status": status})
        if observer:
            await observer(stage, status, {})

    @staticmethod
    def _eligible_evidence(
        evidence: list[EvidenceItem], session: TradingSession
    ) -> list[EvidenceItem]:
        eligible: list[EvidenceItem] = []
        for item in evidence:
            timing = classify_event(item.published_at, session)
            if item.role == EvidenceRole.CAUSAL_INPUT and not timing.eligible_same_day_cause:
                item = item.model_copy(update={"role": EvidenceRole.RETROSPECTIVE_CONTEXT})
            eligible.append(item)
        return eligible

    @staticmethod
    def _non_trading_report(
        ticker: str,
        trade_date: date,
        session: TradingSession,
        instrument,
        trace: list[dict[str, str]],
    ) -> InvestigationReport:
        return InvestigationReport(
            case_id=str(uuid4()),
            run_id=str(uuid4()),
            status=InvestigationStatus.COMPLETED,
            outcome=InvestigationOutcome.INCOMPLETE_DATA,
            ticker=ticker,
            trade_date=trade_date,
            timezone_label=session.timezone_label,
            instrument=instrument,
            assessment=PrimaryAssessment(
                summary="The requested date was not an ASX trading session."
            ),
            confidence=score_confidence(
                ConfidenceFeatures(0, 0, 0, 0, 0, 0, has_primary_evidence=False)
            ),
            completeness=CompletenessAssessment(
                score=0,
                status="INCOMPLETE",
                required_capabilities=["asx_trading_session"],
                missing_capabilities=["asx_trading_session"],
            ),
            coverage_status="NOT_A_TRADING_DAY",
            trace=trace,
        )

    @staticmethod
    def _incomplete_market_report(
        ticker: str,
        trade_date: date,
        session: TradingSession,
        instrument,
        reason: str,
        trace: list[dict[str, str]],
    ) -> InvestigationReport:
        gap = CoverageGap(
            gap_id="MARKET_DATA_UNAVAILABLE",
            capability="market_data",
            provider="configured_market_data",
            reason=reason,
            impact="The price move cannot be calculated or causally investigated.",
            retryable=False,
        )
        return InvestigationReport(
            case_id=str(uuid4()),
            run_id=str(uuid4()),
            status=InvestigationStatus.COMPLETED,
            outcome=InvestigationOutcome.INCOMPLETE_DATA,
            ticker=ticker,
            trade_date=trade_date,
            timezone_label=session.timezone_label,
            instrument=instrument,
            assessment=PrimaryAssessment(
                summary="Point-in-time market data is unavailable for the requested session."
            ),
            confidence=score_confidence(
                ConfidenceFeatures(0, 0, 0, 0, 0, 0, has_primary_evidence=False)
            ),
            completeness=CompletenessAssessment(
                score=0,
                status="INCOMPLETE",
                required_capabilities=["market_data"],
                missing_capabilities=["market_data"],
            ),
            coverage_gaps=[gap],
            coverage_status="INCOMPLETE_MARKET_DATA",
            trace=trace,
        )
