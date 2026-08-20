from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from asx_investigator.agent.reasoning import (
    ChallengeResult,
    EvidenceGapRequest,
    HypothesisBatch,
    HypothesisProposal,
    ReasoningUnavailable,
)
from asx_investigator.confidence.calibration import calibration_record_from_evaluation
from asx_investigator.domain.models import EvidenceItem, EvidenceRole, ValidationStatus
from asx_investigator.evaluation.grading import grade_report
from asx_investigator.evaluation.models import EvalCaseManifest
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.live import DataProviderUnavailable
from asx_investigator.providers.market import CorporateAction
from asx_investigator.providers.outcomes import ProviderOutcome, ProviderStatus
from asx_investigator.providers.recorded import RecordedToolGateway

SYDNEY = ZoneInfo("Australia/Sydney")


class FailingReasoner:
    def __init__(self) -> None:
        self.generate_calls = 0
        self.challenge_calls = 0

    async def generate(self, packet):
        self.generate_calls += 1
        raise ReasoningUnavailable("model timeout")

    async def challenge(self, packet, hypotheses):
        self.challenge_calls += 1
        raise AssertionError("challenge must not run after generation failure")


class GapReasoner:
    model_configuration = {"provider": "TEST", "structured_calls_max": "2"}

    def __init__(self) -> None:
        self.generate_calls = 0
        self.challenge_calls = 0

    async def generate(self, packet):
        self.generate_calls += 1
        return HypothesisBatch(
            hypotheses=[
                HypothesisProposal(
                    hypothesis_id="H1",
                    rank=1,
                    statement="Raised production guidance drove the recorded move.",
                    expected_signature="Positive gap and elevated volume.",
                    supporting_assertion_ids=["A1"],
                )
            ],
            evidence_gap=EvidenceGapRequest(
                purpose="Check whether a stronger official source exists.",
                query="BHP production guidance official",
            ),
        )

    async def challenge(self, packet, hypotheses):
        self.challenge_calls += 1
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary="No stronger evidence-backed alternative was identified.",
        )


class CountingGateway:
    def __init__(self) -> None:
        self.delegate = RecordedToolGateway.default()
        self.targeted_calls = 0

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    async def targeted_retrieve(self, ticker, trade_date, query, purpose):
        self.targeted_calls += 1
        return []


class AfterCloseGateway(CountingGateway):
    async def get_evidence(self, ticker, trade_date):
        items = await self.delegate.get_evidence(ticker, trade_date)
        return [
            item.model_copy(update={"published_at": item.published_at.replace(hour=16, minute=10)})
            for item in items
        ]


class DuringSessionGateway(CountingGateway):
    async def get_evidence(self, ticker, trade_date):
        items = await self.delegate.get_evidence(ticker, trade_date)
        return [
            item.model_copy(update={"published_at": item.published_at.replace(hour=12)})
            for item in items
        ]


class MissingMarketGateway(CountingGateway):
    async def get_market_data(self, ticker, trade_date):
        raise DataProviderUnavailable("outside trailing 12-month live window")


class NonPrimaryEvidenceGateway(CountingGateway):
    async def get_evidence(self, ticker, trade_date):
        items = await self.delegate.get_evidence(ticker, trade_date)
        return [items[0].model_copy(update={"authority": "USER_SUPPLIED"})]


class DuplicateEvidenceGateway(CountingGateway):
    async def get_evidence(self, ticker, trade_date):
        items = await self.delegate.get_evidence(ticker, trade_date)
        return [items[0], items[0].model_copy(update={"evidence_id": "E2"})]


class PositiveMechanicalGateway(CountingGateway):
    async def get_corporate_actions(self, ticker, trade_date):
        original = await self.delegate.get_corporate_actions(ticker, trade_date)
        return ProviderOutcome(
            status=ProviderStatus.SUCCESS,
            provider="OFFICIAL_ACTIONS",
            retrieved_at=original.retrieved_at,
            as_of=datetime(2026, 8, 20, 8, 45, tzinfo=SYDNEY),
            coverage="COMPLETE",
            data=[
                CorporateAction(
                    action_type="SPLIT",
                    effective_date=trade_date,
                    announced_at=datetime(2026, 8, 20, 8, 30, tzinfo=SYDNEY),
                    adjustment_factor=2.0,
                    source_id="action-1",
                )
            ],
        )


class RetrospectiveCorporateActionGateway(CountingGateway):
    async def get_corporate_actions(self, ticker, trade_date):
        original = await self.delegate.get_corporate_actions(ticker, trade_date)
        return ProviderOutcome(
            status=ProviderStatus.SUCCESS,
            provider="OFFICIAL_ACTIONS",
            retrieved_at=original.retrieved_at,
            coverage="COMPLETE",
            data=[
                CorporateAction(
                    action_type="SPLIT",
                    effective_date=trade_date,
                    adjustment_factor=2.0,
                    source_id="retrospective-action-1",
                )
            ],
        )

    async def get_evidence(self, ticker, trade_date):
        return []


class FutureEffectiveCorporateActionGateway(CountingGateway):
    async def get_corporate_actions(self, ticker, trade_date):
        original = await self.delegate.get_corporate_actions(ticker, trade_date)
        return ProviderOutcome(
            status=ProviderStatus.SUCCESS,
            provider="OFFICIAL_ACTIONS",
            retrieved_at=original.retrieved_at,
            as_of=datetime(2026, 8, 20, 8, 45, tzinfo=SYDNEY),
            coverage="COMPLETE",
            data=[
                CorporateAction(
                    action_type="SPLIT",
                    effective_date=trade_date + timedelta(days=1),
                    announced_at=datetime(2026, 8, 20, 8, 30, tzinfo=SYDNEY),
                    adjustment_factor=2.0,
                    source_id="future-effective-action-1",
                )
            ],
        )

    async def get_evidence(self, ticker, trade_date):
        return []


class FailedCorporateActionsGateway(CountingGateway):
    async def get_corporate_actions(self, ticker, trade_date):
        original = await self.delegate.get_corporate_actions(ticker, trade_date)
        return ProviderOutcome(
            status=ProviderStatus.RETRYABLE_FAILURE,
            provider=original.provider,
            retrieved_at=original.retrieved_at,
            coverage="UNAVAILABLE",
            error_code="temporary-corporate-actions-outage",
        )

    async def get_evidence(self, ticker, trade_date):
        return []


class EmptyCorporateActionsDividendGateway(CountingGateway):
    async def get_corporate_actions(self, ticker, trade_date):
        original = await self.delegate.get_corporate_actions(ticker, trade_date)
        return ProviderOutcome(
            status=ProviderStatus.EMPTY,
            provider=original.provider,
            retrieved_at=original.retrieved_at,
            coverage="COMPLETE",
        )

    async def get_evidence(self, ticker, trade_date):
        original = (await self.delegate.get_evidence(ticker, trade_date))[0]
        return [
            EvidenceItem(
                evidence_id="E1",
                source_name="BHP Investor Relations",
                source_url=original.source_url,
                published_at=original.published_at,
                retrieved_at=original.retrieved_at,
                role=EvidenceRole.CAUSAL_INPUT,
                authority="PRIMARY_ISSUER",
                title="Capital management update",
                passage=(
                    "BHP announced a dividend and raised FY26 production guidance "
                    "before market open."
                ),
                content_hash="issuer-dividend-guidance-v1",
                locator="Recorded issuer disclosure",
            )
        ]


class DividendReasoner:
    model_configuration = {"provider": "TEST", "structured_calls_max": "2"}

    async def generate(self, packet):
        return HypothesisBatch(
            hypotheses=[
                HypothesisProposal(
                    hypothesis_id="H1",
                    rank=1,
                    statement=(
                        "BHP announced a dividend and raised production guidance "
                        "before market open."
                    ),
                    expected_signature="Positive gap and elevated volume.",
                    supporting_assertion_ids=["A1"],
                )
            ]
        )

    async def challenge(self, packet, hypotheses):
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary="The supplied issuer assertion is time eligible.",
        )


class ConflictingEvidenceIdGateway(CountingGateway):
    async def get_evidence(self, ticker, trade_date):
        original = (await self.delegate.get_evidence(ticker, trade_date))[0]
        return [
            original,
            original.model_copy(
                update={
                    "passage": "A different frozen disclosure with the same evidence ID.",
                    "content_hash": "different-content-hash",
                }
            ),
        ]


class NaiveEvidenceGateway(CountingGateway):
    async def get_evidence(self, ticker, trade_date):
        original = (await self.delegate.get_evidence(ticker, trade_date))[0]
        return [
            EvidenceItem.model_construct(
                **{
                    **original.model_dump(),
                    "published_at": original.published_at.replace(tzinfo=None),
                }
            )
        ]


async def test_model_failure_preserves_market_facts_and_abstains() -> None:
    reasoner = FailingReasoner()
    report = await InvestigationService(
        RecordedToolGateway.default(), reasoner=reasoner
    ).investigate("BHP", "2026-08-20", mode="LIVE")

    assert report.market_move is not None
    assert report.outcome == "INSUFFICIENT_EVIDENCE"
    assert report.assessment.primary_claim_id is None
    assert all(claim.claim_type != "CAUSE" for claim in report.claims)
    assert reasoner.generate_calls == 1
    assert reasoner.challenge_calls == 0


async def test_reasoning_uses_at_most_two_model_calls_and_one_targeted_retrieval() -> None:
    reasoner = GapReasoner()
    gateway = CountingGateway()

    report = await InvestigationService(gateway, reasoner=reasoner).investigate(
        "BHP", "2026-08-20", mode="LIVE"
    )

    assert report.outcome == "EXPLAINED"
    assert reasoner.generate_calls == 1
    assert reasoner.challenge_calls == 1
    assert gateway.targeted_calls == 1
    assert report.hypotheses[0].status == "LEADING"


async def test_after_close_evidence_cannot_support_same_day_causation() -> None:
    report = await InvestigationService(AfterCloseGateway()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.outcome == "NO_IDENTIFIABLE_CATALYST"
    assert report.evidence[0].role == "RETROSPECTIVE_CONTEXT"
    assert report.assessment.primary_claim_id is None


async def test_during_session_evidence_requires_intraday_timing_resolution() -> None:
    report = await InvestigationService(
        DuringSessionGateway(), reasoner=GapReasoner()
    ).investigate("BHP", "2026-08-20", mode="LIVE")

    assert "TIMING_UNRESOLVED" in report.confidence.applied_caps
    assert "INTRADAY_DATA_MISSING" in report.confidence.applied_caps


async def test_unavailable_point_in_time_market_data_returns_incomplete_outcome() -> None:
    report = await InvestigationService(MissingMarketGateway()).investigate(
        "BHP", "2026-08-20", mode="LIVE"
    )

    assert report.status == "COMPLETED"
    assert report.outcome == "INCOMPLETE_DATA"
    assert report.market_move is None
    assert report.coverage_gaps[0].capability == "market_data"


async def test_non_primary_causal_evidence_cannot_claim_the_primary_source_factor() -> None:
    report = await InvestigationService(
        NonPrimaryEvidenceGateway(), reasoner=GapReasoner()
    ).investigate("BHP", "2026-08-20", mode="LIVE")

    assert "NO_PRIMARY_EVIDENCE" in report.confidence.applied_caps
    assert "Temporally eligible primary evidence" not in report.confidence.positive_factors
    assert report.claim_support[0].band == "MEDIUM"


async def test_duplicate_content_is_removed_before_claim_ids_are_generated() -> None:
    report = await InvestigationService(DuplicateEvidenceGateway()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert [item.evidence_id for item in report.evidence] == ["E1"]
    assert report.claims[0].supporting_evidence_ids == ["E1"]


async def test_positive_corporate_action_becomes_a_cited_mechanical_explanation() -> None:
    report = await InvestigationService(PositiveMechanicalGateway()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.outcome == "EXPLAINED"
    assert report.hypotheses[0].driver_label == "MECHANICAL"
    assert report.claims[0].supporting_evidence_ids == ["M1"]
    assert report.evidence[0].locator == "action-1"


async def test_retroactively_retrieved_effective_action_cannot_explain_same_day_move() -> None:
    report = await InvestigationService(RetrospectiveCorporateActionGateway()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.outcome == "INSUFFICIENT_EVIDENCE"
    assert all(item.driver_label != "MECHANICAL" for item in report.hypotheses)
    assert all(item.evidence_kind != "CORPORATE_ACTION" for item in report.evidence)
    assert all(claim.claim_type != "CAUSE" for claim in report.claims)
    assert {gap.gap_id for gap in report.coverage_gaps} == {
        "CORPORATE_ACTIONS_TEMPORALITY_UNVERIFIED"
    }


async def test_temporal_grader_rejects_mechanical_claim_without_provider_snapshot() -> None:
    report = await InvestigationService(PositiveMechanicalGateway()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )
    manifest = EvalCaseManifest(
        case_id="mechanical-snapshot-required",
        category="MECHANICAL",
        scenario="A mechanical claim requires a point-in-time provider snapshot.",
        ticker="BHP",
        trade_date=report.trade_date,
        evidence_cutoff=report.evidence[0].retrieved_at,
        driver_labels=["MECHANICAL"],
        acceptable_alternatives=[],
        required_evidence_ids=["M1"],
        future_evidence_blacklist=[],
        mechanical_flags=[],
        coverage_expectation="COMPLETE",
        abstention_policy="FORBIDDEN",
        expected_outcome="EXPLAINED",
    )
    tampered = report.model_copy(
        update={
            "provider_diagnostics": [
                item.model_copy(update={"as_of": None})
                if item.operation == "corporate_actions"
                else item
                for item in report.provider_diagnostics
            ]
        }
    )

    evaluation = grade_report(manifest, tampered, latency_ms=1, estimated_cost_aud=0.0)

    temporal_check = next(
        item for item in evaluation.checks if item.name == "temporal_integrity"
    )
    assert temporal_check.passed is False


async def test_future_effective_action_cannot_explain_current_session_move() -> None:
    report = await InvestigationService(FutureEffectiveCorporateActionGateway()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.outcome == "INSUFFICIENT_EVIDENCE"
    assert all(item.driver_label != "MECHANICAL" for item in report.hypotheses)
    assert all(item.evidence_kind != "CORPORATE_ACTION" for item in report.evidence)
    assert {gap.gap_id for gap in report.coverage_gaps} == {
        "CORPORATE_ACTIONS_TEMPORALITY_UNVERIFIED"
    }


async def test_required_corporate_actions_failure_never_becomes_no_catalyst() -> None:
    report = await InvestigationService(FailedCorporateActionsGateway()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.outcome == "INCOMPLETE_DATA"
    assert report.coverage_status == "INCOMPLETE_REQUIRED_PROVIDER"
    assert report.completeness.status == "PARTIAL"
    assert {gap.capability for gap in report.coverage_gaps} == {"corporate_actions"}
    mechanical_validation = next(
        item for item in report.validation_results if item.kind == "CORPORATE_ACTION_CHECK"
    )
    assert "unavailable" in mechanical_validation.summary

    manifest = EvalCaseManifest(
        case_id="corporate-actions-failure",
        category="provider_failure",
        scenario="required corporate-action feed unavailable",
        ticker="BHP",
        trade_date=report.trade_date,
        evidence_cutoff=datetime(
            2026, 8, 20, 16, 0, tzinfo=report.evidence[0].retrieved_at.tzinfo
        )
        if report.evidence
        else datetime(
            2026,
            8,
            20,
            16,
            0,
            tzinfo=report.provider_diagnostics[-1].retrieved_at.tzinfo,
        ),
        driver_labels=["ISSUER_DISCLOSURE"],
        acceptable_alternatives=[],
        required_evidence_ids=[],
        future_evidence_blacklist=[],
        mechanical_flags=[],
        coverage_expectation="INCOMPLETE_REQUIRED_PROVIDER",
        abstention_policy="REQUIRED",
        expected_outcome="INCOMPLETE_DATA",
    )
    tampered = report.model_copy(update={"outcome": "NO_IDENTIFIABLE_CATALYST"})
    evaluation = grade_report(
        manifest, tampered, latency_ms=1, estimated_cost_aud=0.0
    )

    provider_check = next(
        check for check in evaluation.checks if check.name == "provider_failure_semantics"
    )
    assert provider_check.passed is False


async def test_allowed_abstention_is_not_a_passing_attribution_observation() -> None:
    report = await InvestigationService(
        RecordedToolGateway.default(), reasoner=FailingReasoner()
    ).investigate("BHP", "2026-08-20", mode="RECORDED")
    manifest = EvalCaseManifest(
        case_id="allowed-abstention",
        category="ambiguous",
        scenario="model is unavailable and abstention is allowed",
        ticker="BHP",
        trade_date=report.trade_date,
        evidence_cutoff=report.evidence[0].retrieved_at,
        driver_labels=["ISSUER_DISCLOSURE"],
        acceptable_alternatives=[],
        required_evidence_ids=["E1"],
        future_evidence_blacklist=[],
        mechanical_flags=["CHECKED_NO_EVENT"],
        coverage_expectation="COMPLETE",
        abstention_policy="ALLOWED",
        expected_outcome="INSUFFICIENT_EVIDENCE",
    )

    evaluation = grade_report(manifest, report, latency_ms=1, estimated_cost_aud=0.0)
    checks = {check.name: check for check in evaluation.checks}
    record = calibration_record_from_evaluation(
        report,
        evaluation,
        cohort="DEVELOPMENT",
        material_error=False,
    )

    assert checks["top_1_attribution"].passed is False
    assert checks["top_1_attribution"].hard_gate is False
    assert checks["top_2_attribution"].passed is False
    assert checks["top_2_attribution"].hard_gate is False
    assert record.abstained is True
    assert record.checks["top_1"] is False
    assert record.checks["top_2"] is False


async def test_issuer_dividend_prose_cannot_manufacture_a_mechanical_explanation() -> None:
    report = await InvestigationService(
        EmptyCorporateActionsDividendGateway(), DividendReasoner()
    ).investigate("BHP", "2026-08-20", mode="LIVE")

    mechanical = next(
        test for test in report.mechanism_tests if test.mechanism == "MECHANICAL"
    )
    assert mechanical.status == ValidationStatus.NOT_AVAILABLE
    assert report.outcome == "EXPLAINED"
    assert report.hypotheses[0].driver_label == "ISSUER_DISCLOSURE"
    assert "leading mechanical" not in report.claims[0].text.lower()


async def test_conflicting_evidence_id_fails_closed_before_claim_compilation() -> None:
    with pytest.raises(ValueError, match="evidence ID collision"):
        await InvestigationService(ConflictingEvidenceIdGateway()).investigate(
            "BHP", "2026-08-20", mode="RECORDED"
        )


async def test_naive_evidence_timestamp_fails_closed_before_session_classification() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await InvestigationService(NaiveEvidenceGateway()).investigate(
            "BHP", "2026-08-20", mode="RECORDED"
        )
