from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from datetime import date, datetime
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
from asx_investigator.confidence.scoring import (
    ConfidenceFeatures,
    assess_claim_support,
    requires_abstention,
    score_confidence,
)
from asx_investigator.domain.models import (
    CausalMechanism,
    Claim,
    ClaimType,
    CompletenessAssessment,
    CoverageGap,
    EvidenceItem,
    EvidenceRole,
    HypothesisStatus,
    InvestigationOutcome,
    InvestigationReport,
    InvestigationStatus,
    IssuerReferenceFact,
    PrimaryAssessment,
    ProviderCallDiagnostic,
    TradingSession,
    ValidationResult,
    ValidationStatus,
)
from asx_investigator.evidence.context import EvidencePacket, build_evidence_packet
from asx_investigator.evidence.validation import validate_claims
from asx_investigator.investigation.assertions import build_assertions
from asx_investigator.investigation.checkpoints import (
    CHECKPOINT_POLICY_VERSION,
    CHECKPOINT_SCHEMA_VERSION,
    DURABLE_STAGE_ORDER,
    CheckpointEnvelope,
    InvestigationState,
    MarketDataCheckpoint,
)
from asx_investigator.investigation.claim_compiler import (
    ClaimCompilationError,
    compile_claim,
)
from asx_investigator.investigation.ledger import LEDGER_SCHEMA_VERSION, LedgerBuilder
from asx_investigator.investigation.mechanisms import run_mechanism_tests
from asx_investigator.investigation.planning import RetrievalPlanner
from asx_investigator.market.forensics import calculate_market_move
from asx_investigator.market.sessions import (
    classify_event,
    resolve_case_context_as_of,
    resolve_session,
)
from asx_investigator.providers.errors import DataProviderUnavailable
from asx_investigator.providers.market import action_is_same_day_causal
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus
from asx_investigator.providers.protocols import InvestigationTools

StageObserver = Callable[[str, str, dict[str, object]], Awaitable[None]]
StageCompletion = Callable[[str], Awaitable[None]]


class InvestigationKernel:
    """Own the typed evidence-first investigation state machine."""

    def __init__(
        self,
        tools: InvestigationTools,
        reasoner: InvestigationReasoner | None = None,
        planner: RetrievalPlanner | None = None,
    ) -> None:
        self.tools = tools
        self.reasoner = reasoner
        self.planner = planner or RetrievalPlanner()

    async def run(
        self,
        ticker: str,
        trade_date: str | date,
        mode: str = "LIVE",
        on_stage: StageObserver | None = None,
        supplied_evidence: list[EvidenceItem] | None = None,
        primary_only: bool = False,
        excluded_evidence_ids: list[str] | None = None,
        evidence_cutoff: datetime | None = None,
        version_id: str | None = None,
        request_artifact_hash: str | None = None,
        input_artifact_hashes: list[str] | None = None,
        resume_checkpoint: CheckpointEnvelope | None = None,
        context_facts: list[IssuerReferenceFact] | None = None,
        context_as_of: datetime | None = None,
    ) -> InvestigationReport:
        normalized_ticker = ticker.upper().strip()
        admitted_context_facts = list(context_facts or [])
        requested_date = (
            date.fromisoformat(trade_date) if isinstance(trade_date, str) else trade_date
        )
        resolved_context_as_of = context_as_of or resolve_case_context_as_of(
            requested_date, evidence_cutoff
        )
        if resolved_context_as_of.tzinfo is None:
            raise ValueError("context_as_of must include a timezone")
        if version_id is None and resume_checkpoint is not None:
            raise ValueError("resume_checkpoint requires a durable version_id")
        if version_id is not None and request_artifact_hash is None:
            raise ValueError("checkpointing requires a sealed request artifact hash")

        if resume_checkpoint is not None:
            if resume_checkpoint.policy_version != CHECKPOINT_POLICY_VERSION:
                raise ValueError("checkpoint policy is not supported")
            if resume_checkpoint.schema_version != CHECKPOINT_SCHEMA_VERSION:
                raise ValueError("checkpoint schema is not supported")
            state = InvestigationState.model_validate(resume_checkpoint.typed_state_json)
            current_input_hashes = sorted(set(input_artifact_hashes or []))
            if (
                request_artifact_hash is not None
                and request_artifact_hash not in current_input_hashes
            ):
                current_input_hashes.append(request_artifact_hash)
            if state.version_id != version_id or resume_checkpoint.version_id != version_id:
                raise ValueError("checkpoint version does not match the investigation version")
            if state.request_artifact_hash != request_artifact_hash:
                raise ValueError("checkpoint request artifact does not match")
            if sorted(state.initial_input_artifact_hashes) != sorted(current_input_hashes):
                raise ValueError("checkpoint input artifacts do not match current inputs")
            if sorted(resume_checkpoint.input_artifact_hashes) != state.input_hashes():
                raise ValueError("checkpoint input artifacts do not match its typed state")
            if sorted(resume_checkpoint.output_artifact_hashes) != state.output_hashes():
                raise ValueError("checkpoint output artifacts do not match its typed state")
            if state.completed_stage != resume_checkpoint.stage:
                raise ValueError("checkpoint stage does not match its typed state")
            if state.packet is not None and sorted(
                fact.ledger_hash for fact in state.packet.context_facts
            ) != sorted(fact.ledger_hash for fact in admitted_context_facts):
                raise ValueError("checkpoint context facts do not match current inputs")
            if (
                state.packet is not None
                and state.packet.context_as_of != resolved_context_as_of
            ):
                raise ValueError("checkpoint context as-of does not match current inputs")
            trace = list(state.trace)
            trace.append({"node": resume_checkpoint.stage, "status": "RESUMED"})
        else:
            initial_hashes = sorted(set(input_artifact_hashes or []))
            if request_artifact_hash is not None and request_artifact_hash not in initial_hashes:
                initial_hashes.append(request_artifact_hash)
            state = InvestigationState(
                version_id=version_id or "direct-investigation",
                request_artifact_hash=request_artifact_hash or "0" * 64,
                initial_input_artifact_hashes=initial_hashes or ["0" * 64],
                ledger_schema_version=LEDGER_SCHEMA_VERSION,
            )
            trace = []

        model_configuration = (
            getattr(
                self.reasoner,
                "model_configuration",
                {"provider": "INJECTED_REASONER", "structured_calls_max": "2"},
            )
            if self.reasoner
            else {"provider": "RECORDED_DETERMINISTIC", "structured_calls_max": "0"}
        )
        ledger = LedgerBuilder(state.ledger)
        if resume_checkpoint is not None:
            ledger.append(
                stage=resume_checkpoint.stage,
                status="RESUMED",
                input_hashes=state.ledger_input_hashes(resume_checkpoint.stage),
                output_hashes=state.ledger_output_hashes(resume_checkpoint.stage),
                policy_version=CHECKPOINT_POLICY_VERSION,
                model_configuration=model_configuration,
            )
            state.ledger = ledger.entries()

        async def completed(stage: str) -> None:
            previous_boundary = (
                -1
                if state.completed_stage is None
                else DURABLE_STAGE_ORDER.index(state.completed_stage)
            )
            current_boundary = DURABLE_STAGE_ORDER.index(stage)
            for skipped_stage in DURABLE_STAGE_ORDER[
                previous_boundary + 1 : current_boundary
            ]:
                state.capture_ledger_output(skipped_stage)
                ledger.append(
                    stage=skipped_stage,
                    status="SKIPPED",
                    input_hashes=state.ledger_input_hashes(skipped_stage),
                    output_hashes=state.ledger_output_hashes(skipped_stage),
                    policy_version=CHECKPOINT_POLICY_VERSION,
                    model_configuration=model_configuration,
                )
            trace.append({"node": stage, "status": "COMPLETED"})
            state.complete(stage)
            state.capture_ledger_output(stage)
            ledger.append(
                stage=stage,
                status="COMPLETED",
                input_hashes=state.ledger_input_hashes(stage),
                output_hashes=state.ledger_output_hashes(stage),
                policy_version=CHECKPOINT_POLICY_VERSION,
                model_configuration=model_configuration,
            )
            state.ledger = ledger.entries()
            state.trace = list(trace)
            payload: dict[str, object] = {}
            if version_id is not None:
                typed_state_json = state.model_dump(mode="json")
                InvestigationState.model_validate(typed_state_json)
                checkpoint = CheckpointEnvelope(
                    version_id=version_id,
                    stage=stage,
                    input_artifact_hashes=state.input_hashes(),
                    output_artifact_hashes=state.output_hashes(),
                    typed_state_json=typed_state_json,
                    policy_version=CHECKPOINT_POLICY_VERSION,
                )
                payload["checkpoint"] = checkpoint.model_dump(mode="json")
            if on_stage:
                await on_stage(stage, "COMPLETED", payload)

        if not state.has_completed("resolve_instrument"):
            state.instrument = None
            await self._stage(trace, on_stage, "resolve_instrument", "RUNNING")
            state.instrument = await self.tools.resolve_instrument(normalized_ticker)
            await completed("resolve_instrument")
        instrument = state.instrument

        if not state.has_completed("resolve_asx_session"):
            state.session = None
            await self._stage(trace, on_stage, "resolve_asx_session", "RUNNING")
            state.session = resolve_session(requested_date)
            await completed("resolve_asx_session")
        session = state.session
        if not session.is_trading_day:
            return self._non_trading_report(
                normalized_ticker, requested_date, session, instrument, trace, ledger.entries()
            )

        if not state.has_completed("acquire_market_data"):
            state.market_data = None
            await self._stage(trace, on_stage, "acquire_market_data", "RUNNING")
            try:
                acquired_market_data = await self.tools.get_market_data(
                    normalized_ticker, requested_date
                )
            except DataProviderUnavailable as error:
                await self._stage(trace, on_stage, "acquire_market_data", "INCOMPLETE")
                return self._incomplete_market_report(
                    normalized_ticker,
                    requested_date,
                    session,
                    instrument,
                    str(error),
                    trace,
                    error.outcomes,
                    ledger.entries(),
                )
            benchmark_return = await self.tools.get_benchmark_return(requested_date)
            state.market_data = MarketDataCheckpoint(
                bars=acquired_market_data.bars,
                selected_provider=acquired_market_data.selected_provider,
                outcomes=acquired_market_data.outcomes,
                conflicts=acquired_market_data.conflicts,
                coverage_gap=acquired_market_data.coverage_gap,
                benchmark_return=benchmark_return,
                market_move=calculate_market_move(
                    acquired_market_data.bars, benchmark_return
                ),
            )
            await completed("acquire_market_data")
        market_data = state.market_data.to_result()
        market_move = state.market_data.market_move

        if not state.has_completed("test_mechanical_explanations"):
            state.corporate_actions = None
            await self._stage(trace, on_stage, "test_mechanical_explanations", "RUNNING")
            state.corporate_actions = await self.tools.get_corporate_actions(
                normalized_ticker, requested_date
            )
        corporate_actions = state.corporate_actions
        corporate_action_coverage = corporate_actions.status in {
            ProviderStatus.SUCCESS,
            ProviderStatus.EMPTY,
        }
        actions = list(corporate_actions.data or [])
        causal_actions = [
            action
            for action in actions
            if action_is_same_day_causal(action, corporate_actions, session)
        ]
        unverifiable_actions = [action for action in actions if action not in causal_actions]
        mechanical_summary = (
            "The corporate-action feed was unavailable; no mechanical explanation "
            "was inferred from price fields alone."
            if not corporate_action_coverage
            else (
                f"The authoritative feed returned {len(actions)} corporate actions, "
                f"but {len(unverifiable_actions)} lacked a verifiable announcement "
                "timestamp and point-in-time provider snapshot; those actions remain "
                "non-causal context."
                if unverifiable_actions
                else (
                    f"The authoritative feed returned {len(actions)} corporate actions "
                    "for the session; price fields were not used to invent missing events."
                )
            )
        )
        validations = [
            ValidationResult(
                validation_id="V-MECHANICAL",
                kind="CORPORATE_ACTION_CHECK",
                status=(
                    ValidationStatus.PASS
                    if corporate_action_coverage
                    else ValidationStatus.NOT_AVAILABLE
                ),
                summary=mechanical_summary,
            )
        ]
        mechanical_evidence: list[EvidenceItem] = []
        for index, action in enumerate(causal_actions, start=1):
            assert action.announced_at is not None
            passage = (
                f"{action.action_type} was effective on {action.effective_date.isoformat()}"
                + (
                    f" with adjustment factor {action.adjustment_factor}."
                    if action.adjustment_factor is not None
                    else "."
                )
            )
            mechanical_evidence.append(
                EvidenceItem(
                    evidence_id=f"M{index}",
                    source_name=corporate_actions.provider,
                    source_url="https://eodhd.com/financial-apis/asx-corporate-actions-data-api/",
                    published_at=action.announced_at,
                    retrieved_at=corporate_actions.retrieved_at,
                    role=EvidenceRole.CAUSAL_INPUT,
                    authority="APPROVED_OFFICIAL",
                    title=f"Effective {action.action_type.lower()}",
                    passage=passage,
                    content_hash=hashlib.sha256(passage.encode()).hexdigest(),
                    evidence_kind="CORPORATE_ACTION",
                    locator=action.source_id,
                )
            )
        if not state.has_completed("test_mechanical_explanations"):
            state.validations = list(validations)
            await completed("test_mechanical_explanations")
        else:
            validations = list(state.validations) or validations

        if not state.has_completed("plan_evidence_retrieval"):
            state.retrieval_plan = None
            state.retrieval_results = None
            await self._stage(trace, on_stage, "plan_evidence_retrieval", "RUNNING")
            state.retrieval_plan = self.planner.build(
                instrument=instrument,
                session_date=requested_date,
                move=market_move,
                context_facts=admitted_context_facts,
            )
            # Execution begins in the next durable stage.  Keeping a typed empty
            # result set proves a resumed case reuses this exact sealed plan.
            state.retrieval_results = []
            await completed("plan_evidence_retrieval")

        if not state.has_completed("discover_and_freeze_documents"):
            state.evidence = None
            await self._stage(trace, on_stage, "discover_and_freeze_documents", "RUNNING")
            raw_evidence = mechanical_evidence + await self.tools.get_evidence(
                normalized_ticker, requested_date
            )
            raw_evidence.extend(supplied_evidence or [])
            state.evidence = self._deduplicate_evidence(
                self._eligible_evidence(raw_evidence, session)
            )
            state.evidence = self._apply_evidence_policy(
                state.evidence,
                primary_only=primary_only,
                excluded_evidence_ids=excluded_evidence_ids or [],
                evidence_cutoff=evidence_cutoff,
            )
            await completed("discover_and_freeze_documents")
        evidence = list(state.evidence)

        refinement_limited = bool(
            primary_only or excluded_evidence_ids or evidence_cutoff is not None
        )
        if not state.has_completed("extract_exact_passages"):
            state.coverage_complete = None
            state.coverage_gaps = None
            state.conflicts = None
            await self._stage(trace, on_stage, "extract_exact_passages", "RUNNING")
            state.coverage_complete = await self.tools.disclosure_coverage_complete(
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
                            "A mechanical split, distribution or reconstruction cannot be "
                            "ruled out."
                        ),
                        retryable=(
                            corporate_actions.status == ProviderStatus.RETRYABLE_FAILURE
                        ),
                    )
                )
            elif unverifiable_actions:
                coverage_gaps.append(
                    CoverageGap(
                        gap_id="CORPORATE_ACTIONS_TEMPORALITY_UNVERIFIED",
                        capability="corporate_actions",
                        provider=corporate_actions.provider,
                        reason=(
                            "One or more effective corporate actions lack an announcement "
                            "timestamp or a pre-close point-in-time provider snapshot."
                        ),
                        impact=(
                            "The action remains contextual only and cannot support a same-day "
                            "mechanical explanation."
                        ),
                    )
                )
            if not state.coverage_complete:
                coverage_gaps.append(
                    CoverageGap(
                        gap_id="DISCLOSURE_COVERAGE_PARTIAL",
                        capability="issuer_disclosures",
                        provider="issuer_ir",
                        reason=(
                            "A complete point-in-time issuer disclosure archive was unavailable."
                        ),
                        impact=(
                            "Causal confidence is capped and no-catalyst cannot be concluded."
                        ),
                    )
                )
            if refinement_limited:
                coverage_gaps.append(
                    CoverageGap(
                        gap_id="REFINEMENT_SCOPE_LIMITED",
                        capability="refinement_scope",
                        provider="user_refinement",
                        reason=(
                            "The child version intentionally filtered the acquired evidence set."
                        ),
                        impact="The scoped result cannot establish that no catalyst existed.",
                    )
                )
            state.coverage_gaps = coverage_gaps
            state.conflicts = list(market_data.conflicts)
            await completed("extract_exact_passages")
        coverage_complete = state.coverage_complete
        coverage_gaps = list(state.coverage_gaps or [])
        # A no-catalyst outcome means all required investigation capabilities
        # were observed. Corporate actions are one of those capabilities: a
        # missing or partial response cannot be papered over by issuer coverage.
        effective_coverage_complete = (
            coverage_complete
            and corporate_action_coverage
            and not unverifiable_actions
            and not refinement_limited
        )

        if not state.has_completed("assemble_evidence_packet"):
            state.packet = None
            await self._stage(trace, on_stage, "assemble_evidence_packet", "RUNNING")
            assertions = build_assertions(
                evidence,
                case_version_id=state.version_id,
                session=session,
            )
            state.packet = build_evidence_packet(
                normalized_ticker,
                market_move,
                assertions,
                coverage_gaps,
                market_data.conflicts,
                case_version_id=state.version_id,
                # Reference facts remain typed packet context. They never enter the
                # evidence list, assertion builder, claim compiler or mechanism tests.
                context_facts=admitted_context_facts,
                context_as_of=resolved_context_as_of,
            )
            await completed("assemble_evidence_packet")
        packet = state.packet

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
                primary_only=primary_only,
                excluded_evidence_ids=excluded_evidence_ids or [],
                evidence_cutoff=evidence_cutoff,
                trace=trace,
                on_stage=on_stage,
                checkpoint_state=state,
                completed=completed,
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

        assertions = list(packet.assertions)
        mechanism_tests = run_mechanism_tests(
            assertions,
            evaluated_at=corporate_actions.retrieved_at,
        )
        causal = [item for item in evidence if item.role == EvidenceRole.CAUSAL_INPUT]
        selected = validated.leading if validated else None
        evidence_registry = {item.evidence_id: item for item in evidence}
        selected_support = (
            [
                evidence_registry[evidence_id]
                for evidence_id in selected.supporting_evidence_ids
                if evidence_id in evidence_registry
            ]
            if selected
            else []
        )
        if not corporate_action_coverage:
            # Preserve the model's bounded candidate in the trace, but do not
            # compile or publish a cause while a required mechanical check is
            # unavailable. This is an incomplete investigation, not a failed
            # search for a catalyst.
            selected = None
            selected_support = []
        if selected:
            assertion_by_id = {item.assertion_id: item for item in assertions}
            selected_assertions = [
                assertion_by_id[assertion_id]
                for assertion_id in validated.leading_assertion_ids
                if assertion_id in assertion_by_id
            ]
            mechanism = (
                selected_assertions[0].mechanism_hint
                if selected_assertions
                else CausalMechanism.UNKNOWN
            )
            mechanism_verified = any(
                test.mechanism == mechanism
                and test.status == ValidationStatus.PASS
                and selected_assertions[0].assertion_id in test.supporting_assertion_ids
                for test in mechanism_tests
            ) if selected_assertions else False
            try:
                if not mechanism_verified:
                    raise ClaimCompilationError("Selected assertion has no passing mechanism test")
                claim = compile_claim(
                    ticker=normalized_ticker,
                    mechanism=mechanism,
                    assertions=selected_assertions,
                    model_statement=None,
                )
            except ClaimCompilationError as error:
                reasoning_error = str(error)
                validations.append(
                    ValidationResult(
                        validation_id="V-CLAIM-COMPILATION",
                        kind="ASSERTION_CLAIM_COMPILATION",
                        status=ValidationStatus.FAIL,
                        summary=reasoning_error,
                    )
                )
                selected = None
            else:
                outcome = InvestigationOutcome.EXPLAINED
                primary = PrimaryAssessment(primary_claim_id="C1", summary=claim.text)
        else:
            claim = None
        if not selected:
            summary = (
                "No contemporaneous primary evidence was found after complete required "
                "coverage checks."
                if not causal and effective_coverage_complete
                else "The investigation is incomplete because a required provider or evidence "
                "coverage check is unavailable."
                if not corporate_action_coverage
                else "The available evidence cannot support a validated causal explanation."
            )
            claim = Claim(claim_id="C1", claim_type=ClaimType.UNRESOLVED, text=summary)
            outcome = (
                InvestigationOutcome.INCOMPLETE_DATA
                if not corporate_action_coverage
                else InvestigationOutcome.NO_IDENTIFIABLE_CATALYST
                if not causal and effective_coverage_complete and reasoning_error is None
                else InvestigationOutcome.INSUFFICIENT_EVIDENCE
            )
            primary = PrimaryAssessment(primary_claim_id=None, summary=summary)

        await self._stage(trace, on_stage, "confidence_and_abstention", "RUNNING")
        primary_authorities = {
            "PRIMARY_ISSUER",
            "APPROVED_OFFICIAL",
            "USER_SUPPLIED_OFFICIAL",
        }
        has_primary_evidence = any(
            item.authority in primary_authorities for item in selected_support
        )
        selected_timings = [
            classify_event(item.published_at, session) for item in selected_support
        ]
        needs_intraday_data = any(
            item.session_relationship == "DURING_SESSION" for item in selected_timings
        )
        confidence = score_confidence(
            ConfidenceFeatures(
                source_authority=(
                    1.0 if has_primary_evidence else 0.5 if selected_support else 0.2
                ),
                temporal_eligibility=1.0 if selected else 0.0,
                market_signature_fit=0.9 if selected and market_move.is_unusual else 0.4,
                quantitative_consistency=0.9 if market_move.is_unusual else 0.5,
                independent_corroboration=(
                    0.7 if selected and len(selected.supporting_evidence_ids) > 1 else 0.0
                ),
                coverage_completeness=1.0 if effective_coverage_complete else 0.4,
                alternative_strength=(
                    0.4 if validated and len(validated.hypotheses) > 1 else 0.0
                ),
                has_primary_evidence=has_primary_evidence,
                disclosure_coverage_complete=effective_coverage_complete,
                has_material_conflict=bool(market_data.conflicts),
                timing_resolved=not needs_intraday_data,
                needs_intraday_data=needs_intraday_data,
                has_intraday_data=False,
            )
        )
        confidence = confidence.model_copy(
            update={"selected_hypothesis_id": selected.hypothesis_id if selected else None}
        )
        if selected and requires_abstention(confidence):
            outcome = InvestigationOutcome.INSUFFICIENT_EVIDENCE
            claim = Claim(
                claim_id="C1",
                claim_type=ClaimType.UNRESOLVED,
                text="The leading candidate did not clear the minimum confidence band.",
            )
            primary = PrimaryAssessment(primary_claim_id=None, summary=claim.text)
            validated.hypotheses = [
                item.model_copy(
                    update={
                        "status": (
                            HypothesisStatus.INSUFFICIENT_EVIDENCE
                            if item.hypothesis_id == selected.hypothesis_id
                            else item.status
                        )
                    }
                )
                for item in validated.hypotheses
            ]
            validations.append(
                ValidationResult(
                    validation_id="V-ABSTENTION",
                    kind="CONFIDENCE_GATE",
                    status=ValidationStatus.FAIL,
                    summary="LOW confidence candidates are not published as causal explanations.",
                )
            )
        claim.confidence = confidence.score
        validate_claims([claim], evidence_registry)
        claim_support = [assess_claim_support(claim, evidence_registry)]
        await self._stage(trace, on_stage, "confidence_and_abstention", "COMPLETED")

        missing = [gap.capability for gap in coverage_gaps]
        missing_capabilities = missing
        completeness_score = 1.0 if not missing_capabilities and not market_data.conflicts else 0.5
        provider_diagnostics = [
            ProviderCallDiagnostic(
                provider=item.provider,
                operation="daily_bars",
                status=str(item.status),
                coverage=item.coverage,
                retrieved_at=item.retrieved_at,
                as_of=item.as_of,
                provenance=item.provenance,
                error_code=item.error_code,
                source_version=item.source_version,
                artifact_id=(
                    item.artifact.artifact_id if item.artifact is not None else None
                ),
            )
            for item in market_data.outcomes
        ]
        provider_diagnostics.append(
            ProviderCallDiagnostic(
                provider=corporate_actions.provider,
                operation="corporate_actions",
                status=str(corporate_actions.status),
                coverage=corporate_actions.coverage,
                retrieved_at=corporate_actions.retrieved_at,
                as_of=corporate_actions.as_of,
                provenance=corporate_actions.provenance,
                error_code=corporate_actions.error_code,
                source_version=corporate_actions.source_version,
                artifact_id=(
                    corporate_actions.artifact.artifact_id
                    if corporate_actions.artifact is not None
                    else None
                ),
            )
        )
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
            assertions=assertions,
            mechanism_tests=mechanism_tests,
            confidence=confidence,
            claim_support=claim_support,
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
            coverage_status=(
                "INCOMPLETE_REQUIRED_PROVIDER"
                if not corporate_action_coverage
                else "COMPLETE"
                if effective_coverage_complete
                else "SCOPED_REFINEMENT"
                if refinement_limited
                else "PARTIAL_DISCLOSURE_COVERAGE"
            ),
            model_configuration=model_configuration,
            provider_diagnostics=provider_diagnostics,
            ledger=ledger.entries(),
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
        primary_only: bool,
        excluded_evidence_ids: list[str],
        evidence_cutoff: datetime | None,
        trace: list[dict[str, str]],
        on_stage: StageObserver | None,
        checkpoint_state: InvestigationState,
        completed: StageCompletion,
    ) -> tuple[ValidatedReasoning | None, list[EvidenceItem], EvidencePacket]:
        causal = [item for item in packet.assertions if item.causal_eligible]
        if self.reasoner is None:
            if mode.upper() != "RECORDED" or not causal:
                return None, evidence, packet
            if not checkpoint_state.has_completed("deterministic_validation"):
                checkpoint_state.hypothesis_batch = HypothesisBatch(
                    hypotheses=[
                        HypothesisProposal(
                            hypothesis_id="H1",
                            rank=1,
                            driver_label=(
                                "MECHANICAL"
                                if causal[0].mechanism_hint == CausalMechanism.MECHANICAL
                                else "ISSUER_DISCLOSURE"
                            ),
                            statement=causal[0].exact_text,
                            expected_signature=(
                                "Directionally consistent unusual price and volume."
                            ),
                            supporting_assertion_ids=[causal[0].assertion_id],
                        )
                    ]
                )
            if not checkpoint_state.has_completed("deterministic_validation"):
                checkpoint_state.challenge = ChallengeResult(
                    leading_hypothesis_id="H1",
                    timing_leakage=False,
                    unsupported_assumptions=[],
                    summary="The recorded fixture contains no stronger admissible alternative.",
                )
            batch = checkpoint_state.hypothesis_batch
            challenge = checkpoint_state.challenge
            if not checkpoint_state.has_completed("deterministic_validation"):
                await self._stage(trace, on_stage, "deterministic_validation", "RUNNING")
            validated = validate_reasoning(batch, challenge, packet)
            if not checkpoint_state.has_completed("deterministic_validation"):
                await completed("deterministic_validation")
            return validated, evidence, packet

        if not checkpoint_state.has_completed("generate_ranked_hypotheses"):
            checkpoint_state.hypothesis_batch = None
            await self._stage(trace, on_stage, "generate_ranked_hypotheses", "RUNNING")
            checkpoint_state.hypothesis_batch = await self.reasoner.generate(packet)
            await completed("generate_ranked_hypotheses")
        batch = checkpoint_state.hypothesis_batch

        if batch.evidence_gap and not checkpoint_state.has_completed("targeted_retrieval"):
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
                targeted_candidates = [
                    item
                    for item in self._eligible_evidence(retrieved, session)
                    if item.evidence_id not in known
                ]
                evidence.extend(targeted_candidates)
                evidence = self._deduplicate_evidence(evidence)
                evidence = self._apply_evidence_policy(
                    evidence,
                    primary_only=primary_only,
                    excluded_evidence_ids=excluded_evidence_ids,
                    evidence_cutoff=evidence_cutoff,
                )
                assertions = build_assertions(
                    evidence,
                    case_version_id=packet.case_version_id,
                    session=session,
                )
                packet = build_evidence_packet(
                    ticker,
                    market_move,
                    assertions,
                    coverage_gaps,
                    conflicts,
                    case_version_id=packet.case_version_id,
                    context_facts=packet.context_facts,
                    context_as_of=packet.context_as_of,
                )
                checkpoint_state.evidence = list(evidence)
                checkpoint_state.packet = packet
                targeted_evidence_ids = {
                    candidate.evidence_id for candidate in targeted_candidates
                }
                checkpoint_state.targeted_assertion_ids = [
                    item.assertion_id
                    for item in packet.assertions
                    if item.evidence_id in targeted_evidence_ids
                ]
                await completed("targeted_retrieval")

        if not checkpoint_state.has_completed("challenge_leading_hypothesis"):
            checkpoint_state.challenge = None
            await self._stage(trace, on_stage, "challenge_leading_hypothesis", "RUNNING")
            checkpoint_state.challenge = await self.reasoner.challenge(packet, batch)
            await completed("challenge_leading_hypothesis")
        challenge = checkpoint_state.challenge
        if not checkpoint_state.has_completed("deterministic_validation"):
            await self._stage(trace, on_stage, "deterministic_validation", "RUNNING")
        validated = validate_reasoning(
            batch,
            challenge,
            packet,
            targeted_assertion_ids=set(checkpoint_state.targeted_assertion_ids),
        )
        if not checkpoint_state.has_completed("deterministic_validation"):
            await completed("deterministic_validation")
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
        for raw_item in evidence:
            try:
                item = EvidenceItem.model_validate(raw_item.model_dump(mode="python"))
            except ValueError as error:
                raise ValueError("Evidence timestamps must be timezone-aware") from error
            timing = classify_event(item.published_at, session)
            if item.role == EvidenceRole.CAUSAL_INPUT and not timing.eligible_same_day_cause:
                item = item.model_copy(update={"role": EvidenceRole.RETROSPECTIVE_CONTEXT})
            eligible.append(item)
        return eligible

    @staticmethod
    def _deduplicate_evidence(evidence: list[EvidenceItem]) -> list[EvidenceItem]:
        primary_authorities = {
            "PRIMARY_ISSUER",
            "APPROVED_OFFICIAL",
            "USER_SUPPLIED_OFFICIAL",
        }

        def priority(item: EvidenceItem) -> tuple[int, int]:
            return (
                0 if item.role == EvidenceRole.CAUSAL_INPUT else 1,
                0 if item.authority in primary_authorities else 1,
            )

        unique: list[EvidenceItem] = []
        positions: dict[str, int] = {}
        identities: dict[str, dict[str, object]] = {}
        for item in evidence:
            identity = item.model_dump(mode="json")
            prior_identity = identities.get(item.evidence_id)
            if prior_identity is not None and prior_identity != identity:
                raise ValueError(
                    "evidence ID collision has conflicting frozen content or metadata"
                )
            identities[item.evidence_id] = identity
            position = positions.get(item.content_hash)
            if position is None:
                positions[item.content_hash] = len(unique)
                unique.append(item)
            elif priority(item) < priority(unique[position]):
                unique[position] = item
        return unique

    @staticmethod
    def _apply_evidence_policy(
        evidence: list[EvidenceItem],
        *,
        primary_only: bool,
        excluded_evidence_ids: list[str],
        evidence_cutoff: datetime | None,
    ) -> list[EvidenceItem]:
        primary_authorities = {
            "PRIMARY_ISSUER",
            "APPROVED_OFFICIAL",
            "USER_SUPPLIED_OFFICIAL",
        }
        excluded = set(excluded_evidence_ids)
        return [
            item
            for item in evidence
            if item.evidence_id not in excluded
            and (evidence_cutoff is None or item.published_at <= evidence_cutoff)
            and (not primary_only or item.authority in primary_authorities)
        ]

    @staticmethod
    def _non_trading_report(
        ticker: str,
        trade_date: date,
        session: TradingSession,
        instrument,
        trace: list[dict[str, str]],
        ledger,
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
            ledger=ledger,
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
        outcomes: list[ProviderOutcome[object]],
        ledger,
    ) -> InvestigationReport:
        gap = CoverageGap(
            gap_id="MARKET_DATA_UNAVAILABLE",
            capability="market_data",
            provider="configured_market_data",
            reason=reason,
            impact="The price move cannot be calculated or causally investigated.",
            retryable=False,
        )
        provider_diagnostics = [
            ProviderCallDiagnostic(
                provider=item.provider,
                operation="daily_bars",
                status=str(item.status),
                coverage=item.coverage,
                retrieved_at=item.retrieved_at,
                provenance=item.provenance,
                error_code=item.error_code,
                source_version=item.source_version,
                artifact_id=(
                    item.artifact.artifact_id if item.artifact is not None else None
                ),
            )
            for item in outcomes
        ]
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
            provider_diagnostics=provider_diagnostics,
            ledger=ledger,
            trace=trace,
        )
