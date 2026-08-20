from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from asx_investigator.agent.reasoning import ChallengeResult, HypothesisBatch, HypothesisProposal
from asx_investigator.evaluation import gold as gold_evaluation
from asx_investigator.evaluation.bundles import (
    FrozenBundleError,
    load_frozen_gold_corpus,
)
from asx_investigator.evaluation.gold import (
    build_development_calibration_records,
    execute_gold_corpus,
    run_external_gold,
)
from asx_investigator.evaluation.models import GoldExecutionReport, ModelUsageCostArtifact
from tests.unit.evaluation.test_bundles import _bind_metadata_artifact, write_bundle


def _write_holdout_manifest(
    root: Path,
    *,
    metadata_artifact_id: str,
) -> None:
    """Write the label-free sealed-corpus declaration used by the product path."""

    policy = {
        "schema_version": "gold-frozen-v1",
        "corpus_version": "sealed-test-v1",
        "bundle_version": "frozen-case-v1",
        "provider_schema_version": "provider-outcome-v1",
        "policy_schema_version": "phase3-gold-evaluation-v1",
    }
    policy_bytes = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    policy_artifact_id = hashlib.sha256(policy_bytes).hexdigest()
    artifacts = root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / policy_artifact_id).write_bytes(policy_bytes)
    payload = {
        "schema_version": "gold-frozen-v1",
        "corpus_version": "sealed-test-v1",
        "corpus_policy_artifact_id": policy_artifact_id,
        "cases": [
            {
                "case_id": "gold-01",
                "bundle_path": "gold-01",
                "metadata_artifact_id": metadata_artifact_id,
            }
        ],
    }
    (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_development_manifest(
    root: Path,
    *,
    artifact_ids: list[str],
    expected_outcome: str = "EXPLAINED",
    max_cost_aud: float = 1.0,
) -> None:
    payload = {
        "schema_version": "gold-frozen-v1",
        "corpus_version": "synthetic-gold-test-v1",
        "cases": [
            {
                "case_id": "gold-01",
                "bundle_path": "gold-01",
                "ticker": "BHP",
                "trade_date": "2026-08-20",
                "timezone": "Australia/Sydney",
                "evidence_cutoff": "2026-08-20T16:10:00+10:00",
                "artifact_ids": artifact_ids,
                "eligible_evidence_ids": ["E1"],
                "future_evidence_ids": [],
                "driver_labels": ["ISSUER_DISCLOSURE"],
                "acceptable_alternatives": [],
                "mechanical_expectation": "CHECKED_NO_EVENT",
                "coverage_expectation": "COMPLETE",
                "citation_requirements": ["E1"],
                "abstention_policy": "FORBIDDEN",
                "expected_outcome": expected_outcome,
                "max_cost_aud": max_cost_aud,
            }
        ],
    }
    (root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


async def test_gold_runner_executes_a_frozen_bundle_not_a_prebuilt_report(
    tmp_path: Path,
) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    _write_development_manifest(tmp_path, artifact_ids=list(artifacts.values()))
    corpus = load_frozen_gold_corpus(tmp_path, kind="development")

    result = await execute_gold_corpus(corpus, allow_deterministic_fixture=True)

    assert result.status == "PASS"
    assert result.cases[0].report.market_move is not None
    assert result.cases[0].report.ledger
    assert result.cases[0].evaluation is not None
    assert {
        "assertion_integrity",
        "claim_compilation",
        "ledger_reproducibility",
        "calibration_metadata",
    } <= {check.name for check in result.cases[0].evaluation.checks}
    records = build_development_calibration_records(
        result,
        material_errors={"gold-01": False},
    )
    assert records[0].case_id == "gold-01"


class FrozenStructuredReasoner:
    model_configuration = {
        "provider": "FROZEN_TEST_REASONER",
        "model": "frozen-test-v1",
        "structured_calls_max": "2",
    }

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
                    statement="BHP raised FY26 production guidance before ASX trading opened.",
                    expected_signature="Positive gap and elevated volume.",
                    supporting_assertion_ids=["A1"],
                )
            ]
        )

    async def challenge(self, packet, hypotheses):
        self.challenge_calls += 1
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary="The supplied assertion is time eligible.",
        )

    def consume_model_usage_cost_artifacts(self) -> list[ModelUsageCostArtifact]:
        return [
            ModelUsageCostArtifact.recorded(
                model_configuration=self.model_configuration,
                pricing_schedule_version="gemini-aud-test-v1",
                input_tokens=100,
                output_tokens=20,
                measured_cost_aud=0.003,
            ),
            ModelUsageCostArtifact.recorded(
                model_configuration=self.model_configuration,
                pricing_schedule_version="gemini-aud-test-v1",
                input_tokens=80,
                output_tokens=15,
                measured_cost_aud=0.003,
            ),
        ]


class AlternatingProseReasoner(FrozenStructuredReasoner):
    """Emit different private model prose while retaining the same decision IDs."""

    model_configuration = {
        "provider": "FROZEN_TEST_REASONER",
        "model": "alternating-prose-v1",
        "structured_calls_max": "2",
    }

    async def generate(self, packet):
        self.generate_calls += 1
        statement, signature = (
            (
                "BHP raised FY26 production guidance before ASX trading opened.",
                "A positive open gap accompanied the guidance update.",
            )
            if self.generate_calls % 2
            else (
                "Before ASX opened, BHP raised its FY26 production guidance.",
                "Guidance aligns with an upward opening move and high volume.",
            )
        )
        return HypothesisBatch(
            hypotheses=[
                HypothesisProposal(
                    hypothesis_id="H1",
                    rank=1,
                    statement=statement,
                    expected_signature=signature,
                    supporting_assertion_ids=["A1"],
                )
            ]
        )

    async def challenge(self, packet, hypotheses):
        self.challenge_calls += 1
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary=(
                "The first phrasing has no stronger eligible alternative."
                if self.challenge_calls % 2
                else "The second phrasing has no stronger eligible alternative."
            ),
        )


async def test_gold_execution_requires_a_configured_reasoner_unless_fixture_mode_is_explicit(
    tmp_path: Path,
) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    _write_development_manifest(tmp_path, artifact_ids=list(artifacts.values()))
    corpus = load_frozen_gold_corpus(tmp_path, kind="development")

    result = await execute_gold_corpus(corpus)

    assert result.status == "NOT_RUN"
    assert "configured structured reasoner" in result.reason


async def test_gold_execution_records_configured_reasoner_latency_and_measured_cost(
    tmp_path: Path,
) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    _write_development_manifest(tmp_path, artifact_ids=list(artifacts.values()))
    corpus = load_frozen_gold_corpus(tmp_path, kind="development")
    reasoner = FrozenStructuredReasoner()

    result = await execute_gold_corpus(
        corpus,
        reasoner=reasoner,
    )

    assert result.status == "PASS"
    assert reasoner.generate_calls == 2
    assert reasoner.challenge_calls == 2
    assert result.model_configuration == reasoner.model_configuration
    assert result.cases[0].latency_ms is not None
    assert result.cases[0].estimated_cost_aud == 0.012
    assert len(result.cases[0].cost_artifact_hashes) == 4


async def test_gold_reproducibility_ignores_private_model_prose_when_decisions_match(
    tmp_path: Path,
) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    _write_development_manifest(tmp_path, artifact_ids=list(artifacts.values()))
    corpus = load_frozen_gold_corpus(tmp_path, kind="development")

    result = await execute_gold_corpus(
        corpus,
        reasoner=AlternatingProseReasoner(),
    )

    assert result.status == "PASS"
    reproducibility = next(
        check
        for check in result.cases[0].evaluation.checks
        if check.name == "ledger_reproducibility"
    )
    assert reproducibility.passed is True


async def test_external_gold_runner_records_configured_reasoner_cost_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    _write_development_manifest(tmp_path, artifact_ids=list(artifacts.values()))
    corpus = load_frozen_gold_corpus(tmp_path, kind="development")
    monkeypatch.setenv("ASX_EVAL_DEVELOPMENT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        gold_evaluation,
        "load_frozen_gold_corpus",
        lambda *args, **kwargs: corpus,
    )
    reasoner = FrozenStructuredReasoner()

    result = await run_external_gold("development", reasoner=reasoner)

    assert result.status == "PASS"
    assert result.model_configuration == reasoner.model_configuration
    assert result.cases[0].estimated_cost_aud == 0.012
    assert result.cases[0].cost_artifact_hashes


async def test_external_gold_runner_fails_closed_without_immutable_usage_cost_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    _write_development_manifest(tmp_path, artifact_ids=list(artifacts.values()))
    corpus = load_frozen_gold_corpus(tmp_path, kind="development")
    monkeypatch.setenv("ASX_EVAL_DEVELOPMENT_ROOT", str(tmp_path))
    monkeypatch.setattr(
        gold_evaluation,
        "load_frozen_gold_corpus",
        lambda *args, **kwargs: corpus,
    )

    class UnmeteredReasoner(FrozenStructuredReasoner):
        consume_model_usage_cost_artifacts = None

    result = await run_external_gold("development", reasoner=UnmeteredReasoner())

    assert result.status == "NOT_RUN"
    assert "immutable recorded model usage" in (result.reason or "")


async def test_measured_usage_cost_cannot_be_replaced_by_a_tiny_caller_estimate(
    tmp_path: Path,
) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    _write_development_manifest(
        tmp_path,
        artifact_ids=list(artifacts.values()),
        max_cost_aud=0.01,
    )
    corpus = load_frozen_gold_corpus(tmp_path, kind="development")

    result = await execute_gold_corpus(corpus, reasoner=FrozenStructuredReasoner())

    assert result.status == "FAIL"
    assert result.cases[0].estimated_cost_aud == 0.012
    cost = next(
        check for check in result.cases[0].evaluation.checks if check.name == "cost"
    )
    assert cost.passed is False


async def test_missing_external_holdout_is_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASX_EVAL_HOLDOUT_ROOT", raising=False)

    result = await run_external_gold("holdout")

    assert result.status == "NOT_RUN"


def test_failed_development_execution_cannot_form_a_calibration_artifact() -> None:
    with pytest.raises(ValueError, match="passed"):
        build_development_calibration_records(
            GoldExecutionReport(
                corpus="development",
                status="FAIL",
                errors=["gold-01: provider failure"],
            ),
            material_errors={},
        )


def test_development_gold_preserves_its_adjudicated_expected_outcome(
    tmp_path: Path,
) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    _write_development_manifest(
        tmp_path,
        artifact_ids=list(artifacts.values()),
        expected_outcome="NO_IDENTIFIABLE_CATALYST",
    )

    corpus = load_frozen_gold_corpus(tmp_path, kind="development")

    assert corpus.manifests["gold-01"].expected_outcome == "NO_IDENTIFIABLE_CATALYST"


def test_blind_holdout_rejects_an_expected_outcome_label(tmp_path: Path) -> None:
    write_bundle(tmp_path / "gold-01")
    payload = {
        "schema_version": "gold-frozen-v1",
        "corpus_version": "sealed-test-v1",
        "cases": [
            {
                "case_id": "gold-01",
                "bundle_path": "gold-01",
                "expected_outcome": "EXPLAINED",
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FrozenBundleError, match="sealed labels"):
        load_frozen_gold_corpus(tmp_path, kind="holdout")


def test_blind_holdout_rejects_a_nested_report_or_label_field(tmp_path: Path) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    bundle_path = tmp_path / "gold-01" / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["evidence"]["documents"][0]["metadata"]["report"] = {
        "driver_labels": ["ISSUER_DISCLOSURE"]
    }
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    _write_holdout_manifest(tmp_path, metadata_artifact_id=artifacts["metadata"])

    with pytest.raises(FrozenBundleError, match="report|sealed labels"):
        load_frozen_gold_corpus(tmp_path, kind="holdout")


@pytest.mark.parametrize("leaked_field", ("goldLabel", "expectedOutcome", "prebuiltReport"))
def test_blind_holdout_rejects_camel_case_label_aliases(
    tmp_path: Path,
    leaked_field: str,
) -> None:
    root = tmp_path / "gold-01"
    write_bundle(root)
    bundle_path = root / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["evidence"]["documents"][0]["metadata"][leaked_field] = "EXPLAINED"
    metadata_artifact_id = _bind_metadata_artifact(root, bundle)
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    _write_holdout_manifest(tmp_path, metadata_artifact_id=metadata_artifact_id)

    with pytest.raises(FrozenBundleError, match="not allowed|sealed labels"):
        load_frozen_gold_corpus(tmp_path, kind="holdout")


def test_blind_holdout_rejects_arbitrary_unknown_metadata_fields(tmp_path: Path) -> None:
    root = tmp_path / "gold-01"
    write_bundle(root)
    bundle_path = root / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["market"]["unknown_execution_hint"] = {"anything": "EXPLAINED"}
    metadata_artifact_id = _bind_metadata_artifact(root, bundle)
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    _write_holdout_manifest(tmp_path, metadata_artifact_id=metadata_artifact_id)

    with pytest.raises(FrozenBundleError, match="not allowed"):
        load_frozen_gold_corpus(tmp_path, kind="holdout")


def test_blind_holdout_manifest_rejects_replaced_bundle_metadata_at_same_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "gold-01"
    artifacts = write_bundle(root)
    _write_holdout_manifest(tmp_path, metadata_artifact_id=artifacts["metadata"])
    bundle_path = root / "bundle.json"
    replacement = json.loads(bundle_path.read_text(encoding="utf-8"))
    replacement["market"]["benchmark_return"] = 2.0
    _bind_metadata_artifact(root, replacement)
    bundle_path.write_text(json.dumps(replacement), encoding="utf-8")

    with pytest.raises(FrozenBundleError, match="metadata artifact"):
        load_frozen_gold_corpus(tmp_path, kind="holdout")


def test_blind_holdout_accepts_only_label_free_bound_provenance(tmp_path: Path) -> None:
    root = tmp_path / "gold-01"
    artifacts = write_bundle(root)
    _write_holdout_manifest(tmp_path, metadata_artifact_id=artifacts["metadata"])

    corpus = load_frozen_gold_corpus(tmp_path, kind="holdout")

    assert corpus.manifests == {}
    assert corpus.bundles[0].metadata_artifact_id == artifacts["metadata"]


def test_blind_holdout_rejects_serialized_labels_inside_evidence_artifacts(tmp_path: Path) -> None:
    root = tmp_path / "gold-01"
    artifacts = write_bundle(
        root,
        artifact_bytes=b'{"driver_labels":["ISSUER_DISCLOSURE"],"prebuilt_report":{}}',
    )
    _write_holdout_manifest(tmp_path, metadata_artifact_id=artifacts["metadata"])

    with pytest.raises(FrozenBundleError, match="serialized JSON|sealed labels"):
        load_frozen_gold_corpus(tmp_path, kind="holdout")


def test_blind_holdout_rejects_unbound_corpus_policy_schema(tmp_path: Path) -> None:
    root = tmp_path / "gold-01"
    artifacts = write_bundle(root)
    _write_holdout_manifest(tmp_path, metadata_artifact_id=artifacts["metadata"])
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    policy = {
        "schema_version": "gold-frozen-v1",
        "corpus_version": "sealed-test-v1",
        "bundle_version": "unreviewed-bundle-v2",
        "provider_schema_version": "provider-outcome-v1",
        "policy_schema_version": "phase3-gold-evaluation-v1",
    }
    policy_bytes = json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()
    policy_artifact_id = hashlib.sha256(policy_bytes).hexdigest()
    (tmp_path / "artifacts" / policy_artifact_id).write_bytes(policy_bytes)
    manifest["corpus_policy_artifact_id"] = policy_artifact_id
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(FrozenBundleError, match="policy artifact"):
        load_frozen_gold_corpus(tmp_path, kind="holdout")


def test_gold_cli_executes_external_frozen_development_corpus(tmp_path: Path) -> None:
    artifacts = write_bundle(tmp_path / "gold-01")
    _write_development_manifest(tmp_path, artifact_ids=list(artifacts.values()))
    root = Path(__file__).resolve().parents[2]
    environment = {**os.environ, "ASX_EVAL_DEVELOPMENT_ROOT": str(tmp_path)}
    environment.pop("ASX_EVAL_HOLDOUT_ROOT", None)

    completed = subprocess.run(
        [sys.executable, "evals/run_gold_evals.py", "--format", "json"],
        cwd=root,
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 1
    assert payload["development"]["status"] == "FAIL"
    assert "exactly 24" in payload["development"]["errors"][0]
    assert payload["holdout"]["status"] == "NOT_RUN"
