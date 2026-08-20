import json
from datetime import date
from pathlib import Path

import pytest

import evals.run_recorded_evals as eval_runner
from asx_investigator.evaluation.grading import grade_report
from asx_investigator.evaluation.manifests import (
    HoldoutUnavailable,
    load_development_suite,
    load_holdout_suite,
)
from asx_investigator.evaluation.models import EvalCaseManifest
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from evals.run_recorded_evals import run_development_suite


def test_development_suite_has_24_versioned_synthetic_policy_cases() -> None:
    suite = load_development_suite()

    assert suite.suite_version == "phase2-dev-v1"
    assert suite.fixture_kind == "SYNTHETIC_POLICY_SENTINEL"
    assert len(suite.cases) == 24
    assert len({case.case_id for case in suite.cases}) == 24
    assert {
        "DISCLOSURE",
        "MECHANICAL",
        "SECTOR",
        "COMMODITY",
        "MACRO",
        "MULTI_CATALYST",
        "AMBIGUOUS",
        "NO_CATALYST",
    } <= {case.category for case in suite.cases}


def test_holdout_labels_are_loaded_only_from_external_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ASX_EVAL_HOLDOUT_ROOT", raising=False)
    with pytest.raises(HoldoutUnavailable):
        load_holdout_suite()

    defaults = {
        "category": "DISCLOSURE",
        "scenario": "EXTERNAL",
        "ticker": "BHP",
        "trade_date": "2026-08-20",
        "evidence_cutoff": "2026-08-20T16:12:00+10:00",
        "driver_labels": ["ISSUER_DISCLOSURE"],
        "acceptable_alternatives": [],
        "required_evidence_ids": ["E1"],
        "future_evidence_blacklist": [],
        "mechanical_flags": [],
        "coverage_expectation": "COMPLETE",
        "abstention_policy": "FORBIDDEN",
        "expected_outcome": "EXPLAINED",
    }
    payload = {
        "suite_version": "sealed-v1",
        "fixture_kind": "SEALED_POINT_IN_TIME",
        "defaults": defaults,
        "cases": [{"case_id": f"sealed-{index:02d}"} for index in range(1, 13)],
    }
    (tmp_path / "holdout.json").write_text(json.dumps(payload))
    monkeypatch.setenv("ASX_EVAL_HOLDOUT_ROOT", str(tmp_path))

    suite = load_holdout_suite()
    assert suite.suite_version == "sealed-v1"
    assert len(suite.cases) == 12


async def test_grader_reports_raw_hard_gate_checks() -> None:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )
    manifest = EvalCaseManifest(
        case_id="recorded-bhp",
        category="DISCLOSURE",
        scenario="RECORDED_BHP",
        ticker="BHP",
        trade_date=date(2026, 8, 20),
        evidence_cutoff="2026-08-20T16:12:00+10:00",
        driver_labels=["ISSUER_DISCLOSURE"],
        acceptable_alternatives=[],
        required_evidence_ids=["E1"],
        future_evidence_blacklist=[],
        mechanical_flags=[],
        coverage_expectation="COMPLETE",
        abstention_policy="FORBIDDEN",
        expected_outcome="EXPLAINED",
    )

    result = grade_report(manifest, report, latency_ms=20, estimated_cost_aud=0)

    assert result.passed is True
    assert result.raw_counts == {"passed": len(result.checks), "failed": 0}
    assert all(check.passed for check in result.checks)


async def test_all_development_policy_sentinels_execute() -> None:
    result = await run_development_suite()

    assert result.status == "PASSED"
    assert result.raw_counts == {"passed": 24, "failed": 0, "total": 24}


async def test_eval_artifacts_are_replaced_only_when_explicitly_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(eval_runner, "RESULTS_ROOT", tmp_path)

    await eval_runner.main(write_results=False)
    assert list(tmp_path.iterdir()) == []

    await eval_runner.main(write_results=True)
    assert {path.name for path in tmp_path.iterdir()} == {
        "phase2-evaluation.json",
        "phase2-evaluation.md",
    }
