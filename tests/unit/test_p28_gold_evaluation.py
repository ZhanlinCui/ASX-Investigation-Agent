import json
from pathlib import Path

import pytest

from asx_investigator.evaluation.gold import grade_gold_cases, load_gold_corpus
from asx_investigator.evaluation.models import CaseEvaluation, GoldCaseManifest, GraderCheck


def _case(**updates: object) -> dict[str, object]:
    case: dict[str, object] = {
        "case_id": "gold-01",
        "ticker": "BHP",
        "trade_date": "2026-08-20",
        "timezone": "Australia/Sydney",
        "evidence_cutoff": "2026-08-20T16:10:00+10:00",
        "artifact_ids": ["a" * 64],
        "eligible_evidence_ids": ["E1"],
        "future_evidence_ids": [],
        "driver_labels": ["ISSUER_DISCLOSURE"],
        "acceptable_alternatives": [],
        "mechanical_expectation": "CHECKED_NO_EVENT",
        "coverage_expectation": "COMPLETE",
        "citation_requirements": ["E1"],
        "abstention_policy": "FORBIDDEN",
    }
    case.update(updates)
    return case


def _write_manifest(root: Path, cases: list[dict[str, object]]) -> None:
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": "gold-eval-v1", "cases": cases}),
        encoding="utf-8",
    )


def test_absent_external_holdout_is_not_run(monkeypatch) -> None:
    monkeypatch.delenv("ASX_EVAL_HOLDOUT_ROOT", raising=False)

    result = load_gold_corpus("holdout")

    assert result.status == "NOT_RUN"
    assert result.cases == []


def test_gold_manifest_rejects_ambiguous_legacy_abstention_boolean() -> None:
    legacy = _case()
    legacy.pop("abstention_policy")
    legacy["abstention_allowed"] = False

    with pytest.raises(ValueError, match="abstention_allowed"):
        GoldCaseManifest.model_validate(legacy)


def test_gold_manifest_rejects_future_evidence_and_wrong_session(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        [_case(future_evidence_ids=["E1"], trade_date="2026-08-23")],
    )

    result = load_gold_corpus("development", root=tmp_path)

    assert result.status == "FAIL"
    assert "future_evidence_ids" in result.errors[0]


def test_legacy_holdout_loader_never_returns_label_bearing_manifest_data(
    tmp_path: Path,
) -> None:
    sentinel = "DO_NOT_RETURN_SEALED_DRIVER_LABEL"
    _write_manifest(
        tmp_path,
        [
            _case(case_id=f"holdout-{index:02d}", driver_labels=[sentinel])
            for index in range(12)
        ],
    )

    result = load_gold_corpus("holdout", root=tmp_path)

    assert result.status == "FAIL"
    assert result.cases == []
    assert "label-bearing holdout manifests" in result.errors[0]
    assert sentinel not in result.model_dump_json()


def test_legacy_development_loader_remains_available_for_adjudicated_cases(
    tmp_path: Path,
) -> None:
    _write_manifest(
        tmp_path,
        [_case(case_id=f"development-{index:02d}") for index in range(24)],
    )

    result = load_gold_corpus("development", root=tmp_path)

    assert result.status == "PASS"
    assert len(result.cases) == 24
    assert result.cases[0].driver_labels == ["ISSUER_DISCLOSURE"]


def test_release_report_has_raw_counts_proportions_and_case_failures() -> None:
    evaluations = [
        CaseEvaluation(
            case_id="pass",
            passed=True,
            checks=[GraderCheck(name="lookahead", passed=True, detail="ok")],
            raw_counts={"passed": 1, "failed": 0},
            latency_ms=1,
            estimated_cost_aud=0,
        ),
        CaseEvaluation(
            case_id="fail",
            passed=False,
            checks=[GraderCheck(name="lookahead", passed=False, detail="future citation")],
            raw_counts={"passed": 0, "failed": 1},
            latency_ms=1,
            estimated_cost_aud=0,
        ),
    ]

    report = grade_gold_cases(evaluations)

    assert report.raw_counts["lookahead"] == {"passed": 1, "failed": 1}
    assert report.proportions["lookahead"] == 0.5
    assert report.case_failures[0].case_id == "fail"
