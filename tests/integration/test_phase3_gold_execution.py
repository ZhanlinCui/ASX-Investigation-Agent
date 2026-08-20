from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from asx_investigator.evaluation.bundles import (
    FrozenBundleError,
    load_frozen_gold_corpus,
)
from asx_investigator.evaluation.gold import execute_gold_corpus, run_external_gold
from tests.unit.evaluation.test_bundles import write_bundle


def _write_development_manifest(
    root: Path,
    *,
    artifact_ids: list[str],
    expected_outcome: str = "EXPLAINED",
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
                "abstention_allowed": False,
                "expected_outcome": expected_outcome,
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

    result = await execute_gold_corpus(corpus)

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


async def test_missing_external_holdout_is_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASX_EVAL_HOLDOUT_ROOT", raising=False)

    result = await run_external_gold("holdout")

    assert result.status == "NOT_RUN"


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
    write_bundle(tmp_path / "gold-01")
    bundle_path = tmp_path / "gold-01" / "bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["evidence"]["documents"][0]["metadata"]["report"] = {
        "driver_labels": ["ISSUER_DISCLOSURE"]
    }
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    payload = {
        "schema_version": "gold-frozen-v1",
        "corpus_version": "sealed-test-v1",
        "cases": [{"case_id": "gold-01", "bundle_path": "gold-01"}],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FrozenBundleError, match="report|sealed labels"):
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
