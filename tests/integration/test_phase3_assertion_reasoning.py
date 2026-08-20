from asx_investigator.agent.reasoning import ChallengeResult, HypothesisBatch, HypothesisProposal
from asx_investigator.domain.models import InvestigationOutcome
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway


class InvalidAssertionReasoner:
    model_configuration = {"provider": "TEST", "structured_calls_max": "2"}

    async def generate(self, packet):
        return HypothesisBatch(
            hypotheses=[
                HypothesisProposal(
                    hypothesis_id="H1",
                    rank=1,
                    statement="Raised production guidance drove the recorded move.",
                    expected_signature="Positive opening gap and elevated volume.",
                    supporting_assertion_ids=["UNKNOWN"],
                )
            ]
        )

    async def challenge(self, packet, hypotheses):
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary="The candidate references an assertion outside the case packet.",
        )


class NoncausalTargetReasoner:
    model_configuration = {"provider": "TEST", "structured_calls_max": "2"}

    async def generate(self, packet):
        return HypothesisBatch(
            hypotheses=[
                HypothesisProposal(
                    hypothesis_id="H1",
                    rank=1,
                    statement="Raised production guidance drove the recorded move.",
                    expected_signature="Positive opening gap and elevated volume.",
                    supporting_assertion_ids=["A1"],
                )
            ]
        )

    async def challenge(self, packet, hypotheses):
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary="A targeted assertion was accepted without causal eligibility.",
            accepted_targeted_assertion_ids=["A1"],
        )


async def test_unknown_assertion_abstains() -> None:
    report = await InvestigationService(
        RecordedToolGateway.default(), InvalidAssertionReasoner()
    ).investigate("BHP", "2026-08-20", mode="LIVE")

    assert report.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert all(claim.claim_type != "CAUSE" for claim in report.claims)


async def test_noncausal_targeted_assertion_abstains() -> None:
    report = await InvestigationService(
        RecordedToolGateway.default(), NoncausalTargetReasoner()
    ).investigate("BHP", "2026-08-20", mode="LIVE")

    assert report.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert all(claim.claim_type != "CAUSE" for claim in report.claims)
