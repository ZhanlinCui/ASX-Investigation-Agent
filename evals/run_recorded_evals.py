"""Run Phase 2 deterministic development sentinels and optional sealed holdouts."""

# ruff: noqa: E402 -- direct script execution bootstraps the src-layout package.

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from time import perf_counter

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from asx_investigator.agent.reasoning import (
    ChallengeResult,
    EvidenceGapRequest,
    HypothesisBatch,
    HypothesisProposal,
    ReasoningUnavailable,
)
from asx_investigator.domain.models import InvestigationReport
from asx_investigator.evaluation.grading import grade_report
from asx_investigator.evaluation.manifests import (
    HoldoutUnavailable,
    load_development_suite,
    load_holdout_suite,
)
from asx_investigator.evaluation.models import EvalSuiteManifest, EvaluationReport
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway

ROOT = Path(__file__).resolve().parent
RESULTS_ROOT = ROOT / "results"


class ScenarioGateway:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.delegate = RecordedToolGateway.default()

    def __getattr__(self, name: str):
        return getattr(self.delegate, name)

    async def get_evidence(self, ticker, trade_date):
        if self.scenario in {"NO_EVIDENCE", "PARTIAL_NO_EVIDENCE"}:
            return []
        items = await self.delegate.get_evidence(ticker, trade_date)
        if self.scenario == "AFTER_CLOSE":
            return [
                item.model_copy(
                    update={"published_at": item.published_at.replace(hour=16, minute=10)}
                )
                for item in items
            ]
        return items

    async def disclosure_coverage_complete(self, ticker, trade_date):
        return self.scenario != "PARTIAL_NO_EVIDENCE"


class ScenarioReasoner:
    model_configuration = {"provider": "SYNTHETIC_EVAL", "structured_calls_max": "2"}

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario

    async def generate(self, packet):
        if self.scenario == "MODEL_FAILURE":
            raise ReasoningUnavailable("Synthetic model failure sentinel")
        gap = (
            EvidenceGapRequest(
                purpose="Check for a stronger primary issuer source.",
                query="BHP official production guidance",
            )
            if self.scenario == "TARGETED_RETRIEVAL"
            else None
        )
        return HypothesisBatch(
            hypotheses=[
                HypothesisProposal(
                    hypothesis_id="H1",
                    rank=1,
                    driver_label="ISSUER_DISCLOSURE",
                    statement="Raised production guidance drove the synthetic recorded move.",
                    expected_signature="Positive opening gap and elevated volume.",
                    supporting_evidence_ids=["E1"],
                )
            ],
            evidence_gap=gap,
        )

    async def challenge(self, packet, hypotheses):
        return ChallengeResult(
            leading_hypothesis_id="H1",
            timing_leakage=False,
            unsupported_assumptions=[],
            summary="No stronger admissible alternative was present in the synthetic packet.",
        )


async def run_development_suite() -> EvaluationReport:
    suite = load_development_suite()
    results = []
    for manifest in suite.cases:
        gateway = ScenarioGateway(manifest.scenario)
        reasoner = (
            ScenarioReasoner(manifest.scenario)
            if manifest.scenario
            in {"VALID_REASONER", "TARGETED_RETRIEVAL", "MODEL_FAILURE"}
            else None
        )
        mode = "LIVE" if reasoner else "RECORDED"
        started = perf_counter()
        report = await InvestigationService(gateway, reasoner=reasoner).investigate(
            manifest.ticker, manifest.trade_date, mode=mode
        )
        latency_ms = max(1, round((perf_counter() - started) * 1000))
        results.append(
            grade_report(
                manifest,
                report,
                latency_ms=latency_ms,
                estimated_cost_aud=0,
            )
        )
    passed = sum(result.passed for result in results)
    return EvaluationReport(
        suite_version=suite.suite_version,
        fixture_kind=suite.fixture_kind,
        status="PASSED" if passed == len(results) else "FAILED",
        raw_counts={"passed": passed, "failed": len(results) - passed, "total": len(results)},
        proportions={"passed": passed / len(results) if results else 0},
        cases=results,
        limitations=[
            "Synthetic policy sentinels test safety and orchestration, not historical accuracy.",
            "Point-in-time performance requires adjudicated frozen issuer and market snapshots.",
        ],
    )


def run_external_holdout(suite: EvalSuiteManifest, root: Path) -> EvaluationReport:
    results = []
    missing: list[str] = []
    for manifest in suite.cases:
        report_path = root / "reports" / f"{manifest.case_id}.json"
        if not report_path.is_file():
            missing.append(manifest.case_id)
            continue
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        report = InvestigationReport.model_validate(payload["report"])
        results.append(
            grade_report(
                manifest,
                report,
                latency_ms=int(payload.get("latency_ms", 0)),
                estimated_cost_aud=float(payload.get("estimated_cost_aud", 0)),
            )
        )
    if missing:
        return EvaluationReport(
            suite_version=suite.suite_version,
            fixture_kind=suite.fixture_kind,
            status="NOT_RUN",
            raw_counts={
                "provided": len(results),
                "missing": len(missing),
                "total": len(suite.cases),
            },
            proportions={"provided": len(results) / len(suite.cases) if suite.cases else 0},
            cases=results,
            limitations=[f"Missing sealed report artifacts for: {', '.join(missing)}"],
        )
    passed = sum(result.passed for result in results)
    return EvaluationReport(
        suite_version=suite.suite_version,
        fixture_kind=suite.fixture_kind,
        status="PASSED" if passed == len(results) else "FAILED",
        raw_counts={"passed": passed, "failed": len(results) - passed, "total": len(results)},
        proportions={"passed": passed / len(results) if results else 0},
        cases=results,
    )


def _not_run_holdout() -> EvaluationReport:
    return EvaluationReport(
        suite_version="sealed-holdout",
        fixture_kind="SEALED_POINT_IN_TIME",
        status="NOT_RUN",
        raw_counts={"passed": 0, "failed": 0, "total": 0},
        proportions={"passed": 0},
        limitations=["ASX_EVAL_HOLDOUT_ROOT was not provided."],
    )


def render_markdown(development: EvaluationReport, holdout: EvaluationReport) -> str:
    lines = [
        "# Phase 2 Evaluation Report",
        "",
        "## Development policy sentinels",
        "",
        f"- Status: {development.status}",
        f"- Raw counts: {development.raw_counts}",
        f"- Passed proportion: {development.proportions.get('passed', 0):.3f}",
        "",
        "## Sealed point-in-time holdout",
        "",
        f"- Status: {holdout.status}",
        f"- Raw counts: {holdout.raw_counts}",
        "",
        "## Failures",
        "",
    ]
    failures = [case for case in [*development.cases, *holdout.cases] if not case.passed]
    if not failures:
        lines.append("- None in executed cases.")
    for case in failures:
        failed_checks = [check.name for check in case.checks if not check.passed]
        lines.append(f"- {case.case_id}: {', '.join(failed_checks)}")
    lines.extend(["", "## Limitations", ""])
    for limitation in [*development.limitations, *holdout.limitations]:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


async def main(*, write_results: bool = False) -> None:
    development = await run_development_suite()
    try:
        holdout_suite = load_holdout_suite()
        holdout_root = Path(os.environ["ASX_EVAL_HOLDOUT_ROOT"])
        holdout = run_external_holdout(holdout_suite, holdout_root)
    except HoldoutUnavailable:
        holdout = _not_run_holdout()
    payload = {
        "development": development.model_dump(mode="json"),
        "holdout": holdout.model_dump(mode="json"),
    }
    if write_results:
        RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
        (RESULTS_ROOT / "phase2-evaluation.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        (RESULTS_ROOT / "phase2-evaluation.md").write_text(
            render_markdown(development, holdout), encoding="utf-8"
        )
    print(json.dumps(payload, indent=2))
    if development.status != "PASSED" or holdout.status == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-results",
        action="store_true",
        help="replace the versioned JSON and Markdown evaluation artifacts",
    )
    asyncio.run(main(write_results=parser.parse_args().write_results))
