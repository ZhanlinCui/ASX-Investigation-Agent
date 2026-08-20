import asyncio
import json
from datetime import UTC, datetime, timedelta
from time import sleep

from fastapi.testclient import TestClient

from asx_investigator.agent.reasoning import (
    ChallengeResult,
    EvidenceGapRequest,
    HypothesisBatch,
    HypothesisProposal,
)
from asx_investigator.api.app import create_app
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.storage.memory import SharedMemoryRepository
from asx_investigator.storage.repository import SQLiteCaseRepository


class ContextCapturingReasoner:
    model_configuration = {"provider": "TEST", "structured_calls_max": "2"}

    def __init__(self, *, request_targeted_retrieval: bool = False) -> None:
        self.packets = []
        self.challenge_packets = []
        self.request_targeted_retrieval = request_targeted_retrieval

    async def generate(self, packet):
        self.packets.append(packet)
        return HypothesisBatch(
            hypotheses=[
                HypothesisProposal(
                    hypothesis_id="H1",
                    rank=1,
                    statement="BHP raised FY26 production guidance before market open.",
                    expected_signature="Positive opening gap and elevated volume.",
                    supporting_assertion_ids=["A1"],
                )
            ],
            evidence_gap=(
                EvidenceGapRequest(
                    purpose="Confirm the issuer context without treating it as case evidence.",
                    query="BHP issuer context",
                )
                if self.request_targeted_retrieval
                else None
            ),
        )

    async def challenge(self, packet, hypotheses):
        self.challenge_packets.append(packet)
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary="The assertion is time eligible and case scoped.",
        )


def wait_for_report(client: TestClient, case_id: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    for _ in range(60):
        payload = client.get(f"/api/v1/investigations/{case_id}").json()
        if payload["status"] not in {"QUEUED", "RUNNING"}:
            return payload
        sleep(0.01)
    raise AssertionError(f"case did not complete: {payload}")


async def test_direct_service_call_remains_compatible_without_shared_memory() -> None:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.ticker == "BHP"
    assert report.ledger


async def test_context_only_facts_survive_targeted_packet_rebuild(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()
    reference = await memory.put_reference_fact(
        ticker="BHP",
        field="sector",
        value="MEMORY_CONTEXT_ONLY_NOT_CAUSAL",
        source_url="https://issuer.example/profile",
        source_hash="e" * 64,
        valid_until=datetime.now(UTC) + timedelta(days=1),
    )
    reasoner = ContextCapturingReasoner(request_targeted_retrieval=True)

    report = await InvestigationService(
        RecordedToolGateway.default(), reasoner
    ).investigate(
        "BHP",
        "2026-08-20",
        mode="LIVE",
        context_facts=[reference],
    )

    assert reasoner.challenge_packets[0].context_facts == [reference]
    assert reference.value not in report.model_dump_json()


def test_context_only_memory_is_hash_logged_without_cross_case_causal_leakage(tmp_path) -> None:
    database_path = tmp_path / "cases.db"
    memory = SharedMemoryRepository(database_path)
    asyncio.run(memory.initialize())
    reference = asyncio.run(
        memory.put_reference_fact(
            ticker="BHP",
            field="business_description",
            value="MEMORY_CONTEXT_ONLY_NOT_CAUSAL",
            source_url="https://issuer.example/profile",
            source_hash="d" * 64,
            valid_until=datetime.now(UTC) + timedelta(days=1),
        )
    )
    reasoner = ContextCapturingReasoner()
    app = create_app(
        InvestigationService(RecordedToolGateway.default(), reasoner),
        repository=SQLiteCaseRepository(database_path),
    )

    with TestClient(app) as client:
        parent = client.post(
            "/api/v1/investigations",
            json={"ticker": "BHP", "trade_date": "2026-08-20", "mode": "RECORDED"},
        ).json()
        parent_report = wait_for_report(client, parent["case_id"])
        child = client.post(
            f"/api/v1/investigations/{parent['case_id']}/versions",
            json={"primary_only": True},
        ).json()
        child_report = wait_for_report(client, child["case_id"])

    assert len(reasoner.packets) == 2
    assert all(packet.context_facts == [reference] for packet in reasoner.packets)
    assert all(
        reference.entry_id
        not in {
            assertion.evidence_id
            for assertion in packet.assertions
        }
        for packet in reasoner.packets
    )
    assert reference.ledger_hash in child_report["ledger"][0]["input_hashes"]
    assert reference.entry_id not in json.dumps(child_report["ledger"])
    assert reference.value not in json.dumps(child_report)
    assert parent_report["assessment"]["summary"] not in json.dumps(child_report["ledger"])
