from types import SimpleNamespace

from asx_investigator.agent.gemini import GeminiInvestigationReasoner
from asx_investigator.agent.reasoning import ChallengeResult, HypothesisBatch
from asx_investigator.settings import Settings
from tests.unit.agent.test_reasoning import packet


class FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.responses = [
            SimpleNamespace(
                text=(
                    '{"hypotheses":[{"hypothesis_id":"H1","rank":1,'
                    '"statement":"Raised guidance drove the positive price move.",'
                    '"expected_signature":"Positive opening gap and elevated volume.",'
                    '"supporting_evidence_ids":["E1"],'
                    '"contradicting_evidence_ids":[]}]}'
                )
            ),
            SimpleNamespace(
                text=(
                    '{"leading_hypothesis_id":"H1","stronger_alternative_id":null,'
                    '"timing_leakage":false,"unsupported_assumptions":[],'
                    '"summary":"No stronger evidence-backed alternative was identified."}'
                )
            ),
        ]

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses[len(self.calls) - 1]


async def test_gemini_reasoner_makes_two_structured_evidence_bound_calls() -> None:
    models = FakeModels()
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    reasoner = GeminiInvestigationReasoner(Settings(), client=client)

    hypotheses = await reasoner.generate(packet())
    challenge = await reasoner.challenge(packet(), hypotheses)

    assert isinstance(hypotheses, HypothesisBatch)
    assert isinstance(challenge, ChallengeResult)
    assert len(models.calls) == 2
    assert models.calls[0]["config"].response_mime_type == "application/json"
    assert "untrusted data" in models.calls[0]["contents"]
