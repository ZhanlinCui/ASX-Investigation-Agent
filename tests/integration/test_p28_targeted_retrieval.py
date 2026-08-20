from datetime import datetime

from asx_investigator.agent.reasoning import (
    ChallengeResult,
    EvidenceGapRequest,
    HypothesisBatch,
    HypothesisProposal,
)
from asx_investigator.domain.models import EvidenceRole, InvestigationOutcome
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.market.sessions import SYDNEY
from asx_investigator.providers.recorded import RecordedToolGateway


class FrozenTargetGateway:
    def __init__(self) -> None:
        self.delegate = RecordedToolGateway.default()
        self.targeted_calls = 0

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    async def targeted_retrieve(self, ticker, trade_date, query, purpose):
        self.targeted_calls += 1
        base = (await self.delegate.get_evidence(ticker, trade_date))[0]
        return [
            base.model_copy(
                update={
                    "evidence_id": "T1",
                    "title": "Targeted FY26 guidance release",
                    "published_at": datetime(2026, 8, 20, 8, 45, tzinfo=SYDNEY),
                    "role": EvidenceRole.CAUSAL_INPUT,
                    "content_hash": "recorded-bhp-targeted-guidance-v1",
                }
            )
        ]


class TargetAcceptingReasoner:
    model_configuration = {"provider": "TEST", "structured_calls_max": "2"}

    def __init__(self) -> None:
        self.generate_calls = 0
        self.challenge_calls = 0
        self.challenge_packet = None

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
                purpose="Need the issuer release to confirm the supplied announcement.",
                query="BHP production guidance issuer release",
            ),
        )

    async def challenge(self, packet, hypotheses):
        self.challenge_calls += 1
        self.challenge_packet = packet
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary="The targeted issuer release confirms the supplied announcement.",
            accepted_targeted_evidence_ids=["T1"],
        )


async def test_second_call_can_select_only_frozen_targeted_evidence() -> None:
    tools = FrozenTargetGateway()
    reasoner = TargetAcceptingReasoner()

    report = await InvestigationService(tools, reasoner).investigate(
        "BHP", "2026-08-20", mode="LIVE"
    )

    assert report.outcome == InvestigationOutcome.EXPLAINED
    assert report.validation_results[-2].evidence_ids == ["E1", "T1"]
    assert report.claims[0].supporting_evidence_ids == ["E1", "T1"]
    assert reasoner.generate_calls == 1
    assert reasoner.challenge_calls == 1
    assert tools.targeted_calls == 1


async def test_excluded_or_post_cutoff_target_is_not_visible_to_challenge() -> None:
    tools = FrozenTargetGateway()
    reasoner = TargetAcceptingReasoner()

    report = await InvestigationService(tools, reasoner).investigate(
        "BHP",
        "2026-08-20",
        mode="LIVE",
        excluded_evidence_ids=["T1"],
        evidence_cutoff=datetime(2026, 8, 20, 8, 40, tzinfo=SYDNEY),
    )

    assert report.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert "T1" not in reasoner.challenge_packet.allowed_evidence_ids
    assert reasoner.generate_calls == 1
    assert reasoner.challenge_calls == 1
