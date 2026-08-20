from asx_investigator.agent.reasoning import (
    ChallengeResult,
    EvidenceGapRequest,
    HypothesisBatch,
    HypothesisProposal,
    ReasoningUnavailable,
)
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.live import DataProviderUnavailable
from asx_investigator.providers.recorded import RecordedToolGateway


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
                    supporting_evidence_ids=["E1"],
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


class MissingMarketGateway(CountingGateway):
    async def get_market_data(self, ticker, trade_date):
        raise DataProviderUnavailable("outside trailing 12-month live window")


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


async def test_unavailable_point_in_time_market_data_returns_incomplete_outcome() -> None:
    report = await InvestigationService(MissingMarketGateway()).investigate(
        "BHP", "2026-08-20", mode="LIVE"
    )

    assert report.status == "COMPLETED"
    assert report.outcome == "INCOMPLETE_DATA"
    assert report.market_move is None
    assert report.coverage_gaps[0].capability == "market_data"
