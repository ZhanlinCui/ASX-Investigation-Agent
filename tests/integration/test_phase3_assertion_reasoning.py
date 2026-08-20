from asx_investigator.agent.reasoning import ChallengeResult, HypothesisBatch, HypothesisProposal
from asx_investigator.domain.models import InvestigationOutcome
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.report.markdown import render_markdown


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


class ModelProseReasoner:
    model_configuration = {"provider": "TEST", "structured_calls_max": "2"}

    async def generate(self, packet):
        return HypothesisBatch(
            hypotheses=[
                HypothesisProposal(
                    hypothesis_id="H1",
                    rank=1,
                    driver_label="MODEL_DRIVER_PROSE_MUST_NOT_PUBLISH",
                    statement="BHP raised FY26 production guidance before market open.",
                    expected_signature="MODEL_EXPECTED_SIGNATURE_MUST_NOT_PUBLISH",
                    supporting_assertion_ids=["A1"],
                )
            ]
        )

    async def challenge(self, packet, hypotheses):
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary="MODEL_CHALLENGE_SUMMARY_MUST_NOT_PUBLISH",
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


async def test_model_prose_never_reaches_public_report_json_or_markdown() -> None:
    report = await InvestigationService(
        RecordedToolGateway.default(), ModelProseReasoner()
    ).investigate("BHP", "2026-08-20", mode="LIVE")

    public_json = report.model_dump_json()
    markdown = render_markdown(report)
    for model_prose in (
        "MODEL_DRIVER_PROSE_MUST_NOT_PUBLISH",
        "MODEL_EXPECTED_SIGNATURE_MUST_NOT_PUBLISH",
        "MODEL_CHALLENGE_SUMMARY_MUST_NOT_PUBLISH",
    ):
        assert model_prose not in public_json
        assert model_prose not in markdown
