"""External gold-evaluation contracts kept outside investigation context."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from asx_investigator.agent.reasoning import InvestigationReasoner
from asx_investigator.evaluation.bundles import (
    FrozenBundleError,
    FrozenCaseGateway,
    FrozenGoldCorpus,
    load_frozen_gold_corpus,
)
from asx_investigator.evaluation.grading import grade_report, normalized_ledger
from asx_investigator.evaluation.models import (
    CaseEvaluation,
    EvalCaseManifest,
    GoldCaseFailure,
    GoldCaseManifest,
    GoldCorpusLoadResult,
    GoldExecutionCase,
    GoldExecutionReport,
    GoldReleaseReport,
)
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.market.sessions import resolve_session

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ENVIRONMENT_ROOTS = {
    "development": "ASX_EVAL_DEVELOPMENT_ROOT",
    "holdout": "ASX_EVAL_HOLDOUT_ROOT",
}


def load_gold_corpus(corpus: str, *, root: Path | None = None) -> GoldCorpusLoadResult:
    if corpus not in _ENVIRONMENT_ROOTS:
        raise ValueError("corpus must be development or holdout")
    selected_root = root or _environment_root(corpus)
    if selected_root is None:
        return GoldCorpusLoadResult(
            corpus=corpus,
            status="NOT_RUN",
            reason=f"{_ENVIRONMENT_ROOTS[corpus]} was not provided.",
        )
    manifest_path = selected_root / "manifest.json"
    if not manifest_path.is_file():
        return GoldCorpusLoadResult(
            corpus=corpus,
            status="FAIL",
            errors=[f"Gold manifest is missing: {manifest_path}"],
        )
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return GoldCorpusLoadResult(corpus=corpus, status="FAIL", errors=[str(error)])
    if payload.get("schema_version") != "gold-eval-v1":
        return GoldCorpusLoadResult(
            corpus=corpus,
            status="FAIL",
            errors=["schema_version must be gold-eval-v1"],
        )
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        return GoldCorpusLoadResult(corpus=corpus, status="FAIL", errors=["cases must be an array"])
    errors: list[str] = []
    cases: list[GoldCaseManifest] = []
    for index, raw_case in enumerate(raw_cases):
        if not isinstance(raw_case, dict):
            errors.append(f"cases[{index}] must be an object")
            continue
        errors.extend(_validate_raw_case(raw_case, index))
        try:
            cases.append(GoldCaseManifest.model_validate(raw_case))
        except ValidationError as error:
            errors.append(f"cases[{index}]: {error.errors()[0]['msg']}")
    expected_count = 24 if corpus == "development" else 12
    if len(raw_cases) != expected_count:
        errors.append(f"{corpus} corpus must contain exactly {expected_count} cases")
    return GoldCorpusLoadResult(
        corpus=corpus,
        status="FAIL" if errors else "PASS",
        cases=[] if errors else cases,
        errors=errors,
    )


def grade_gold_cases(evaluations: list[CaseEvaluation]) -> GoldReleaseReport:
    if not evaluations:
        return GoldReleaseReport(status="NOT_RUN", raw_counts={}, proportions={})
    counts: dict[str, dict[str, int]] = {}
    failures: list[GoldCaseFailure] = []
    for evaluation in evaluations:
        failed_checks = [check.name for check in evaluation.checks if not check.passed]
        if failed_checks:
            failures.append(
                GoldCaseFailure(
                    case_id=evaluation.case_id,
                    failed_checks=failed_checks,
                )
            )
        for check in evaluation.checks:
            bucket = counts.setdefault(check.name, {"passed": 0, "failed": 0})
            bucket["passed" if check.passed else "failed"] += 1
    proportions = {
        name: values["passed"] / (values["passed"] + values["failed"])
        for name, values in counts.items()
    }
    return GoldReleaseReport(
        status="PASS" if not failures else "FAIL",
        raw_counts=counts,
        proportions=proportions,
        case_failures=failures,
    )


async def execute_gold_corpus(
    corpus: FrozenGoldCorpus,
    *,
    reasoner: InvestigationReasoner | None = None,
) -> GoldExecutionReport:
    """Run frozen provider artifacts through the same kernel as the product.

    A second, independent run checks the stable portion of the resulting ledger.
    Its wall-clock timestamps are intentionally excluded from that comparison.
    """

    cases: list[GoldExecutionCase] = []
    errors: list[str] = []
    for bundle in corpus.bundles:
        started = perf_counter()
        try:
            first = await InvestigationService(
                FrozenCaseGateway(bundle), reasoner=reasoner
            ).investigate(bundle.ticker, bundle.trade_date, mode="RECORDED")
            second = await InvestigationService(
                FrozenCaseGateway(bundle), reasoner=reasoner
            ).investigate(bundle.ticker, bundle.trade_date, mode="RECORDED")
        except (FrozenBundleError, LookupError, ValueError) as error:
            errors.append(f"{bundle.case_id}: execution failed: {error}")
            continue
        latency_ms = round((perf_counter() - started) * 1_000)
        if corpus.kind == "holdout":
            # Keep sealed labels out of the execution object; an external grader
            # may later join this blind report with labels outside this runtime.
            cases.append(GoldExecutionCase(case_id=bundle.case_id, report=first))
            continue
        manifest = corpus.manifests[bundle.case_id]
        evaluation = grade_report(
            _evaluation_manifest(manifest),
            first,
            latency_ms=latency_ms,
            estimated_cost_aud=0.0,
            ledger_reproducible=normalized_ledger(first) == normalized_ledger(second),
        )
        cases.append(
            GoldExecutionCase(
                case_id=bundle.case_id,
                report=first,
                evaluation=evaluation,
            )
        )
    if errors:
        return GoldExecutionReport(
            corpus=corpus.kind,
            corpus_version=corpus.corpus_version,
            status="FAIL",
            cases=cases,
            errors=errors,
        )
    if corpus.kind == "holdout":
        return GoldExecutionReport(
            corpus="holdout",
            corpus_version=corpus.corpus_version,
            status="NOT_RUN",
            cases=cases,
            reason="Blind holdout reports were produced; labels require an external grader.",
        )
    failed = [item.case_id for item in cases if item.evaluation and not item.evaluation.passed]
    return GoldExecutionReport(
        corpus="development",
        corpus_version=corpus.corpus_version,
        status="FAIL" if failed else "PASS",
        cases=cases,
        errors=[f"Development cases failed: {', '.join(failed)}"] if failed else [],
    )


async def run_external_gold(
    corpus: str, *, reasoner: InvestigationReasoner | None = None
) -> GoldExecutionReport:
    """Run a supplied external corpus, never treating an absent root as a pass."""

    if corpus not in _ENVIRONMENT_ROOTS:
        raise ValueError("corpus must be development or holdout")
    root = _environment_root(corpus)
    if root is None:
        return GoldExecutionReport(
            corpus=corpus,
            status="NOT_RUN",
            reason=f"{_ENVIRONMENT_ROOTS[corpus]} was not provided.",
        )
    try:
        frozen = load_frozen_gold_corpus(
            root,
            kind=corpus,
            enforce_release_case_count=True,
        )
    except FrozenBundleError as error:
        return GoldExecutionReport(corpus=corpus, status="FAIL", errors=[str(error)])
    return await execute_gold_corpus(frozen, reasoner=reasoner)


def _environment_root(corpus: str) -> Path | None:
    value = os.environ.get(_ENVIRONMENT_ROOTS[corpus])
    return Path(value) if value else None


def _validate_raw_case(raw_case: dict[str, object], index: int) -> list[str]:
    prefix = f"cases[{index}]"
    future = set(_string_list(raw_case.get("future_evidence_ids")))
    eligible = set(_string_list(raw_case.get("eligible_evidence_ids")))
    errors: list[str] = []
    if future & eligible:
        errors.append(f"{prefix}: future_evidence_ids must not overlap eligible_evidence_ids")
    if raw_case.get("timezone") != "Australia/Sydney":
        errors.append(f"{prefix}: timezone must be Australia/Sydney")
    artifact_ids = _string_list(raw_case.get("artifact_ids"))
    if not artifact_ids or any(_SHA256.fullmatch(value) is None for value in artifact_ids):
        errors.append(f"{prefix}: artifact_ids must be SHA-256 hashes")
    try:
        trade_date = GoldCaseManifest.model_validate(raw_case).trade_date
        if not resolve_session(trade_date).is_trading_day:
            errors.append(f"{prefix}: trade_date must be an ASX trading day")
    except ValidationError:
        pass
    return errors


def _evaluation_manifest(manifest: GoldCaseManifest) -> EvalCaseManifest:
    """Translate externally adjudicated development labels to the stable grader API."""

    return EvalCaseManifest(
        case_id=manifest.case_id,
        category="GOLD",
        scenario="FROZEN_POINT_IN_TIME",
        ticker=manifest.ticker,
        trade_date=manifest.trade_date,
        evidence_cutoff=manifest.evidence_cutoff,
        driver_labels=manifest.driver_labels,
        acceptable_alternatives=manifest.acceptable_alternatives,
        required_evidence_ids=(manifest.citation_requirements or manifest.eligible_evidence_ids),
        future_evidence_blacklist=manifest.future_evidence_ids,
        mechanical_flags=[manifest.mechanical_expectation],
        coverage_expectation=manifest.coverage_expectation,
        abstention_policy="ALLOWED" if manifest.abstention_allowed else "FORBIDDEN",
        expected_outcome=manifest.expected_outcome,
    )


def _string_list(value: object) -> list[str]:
    return value if isinstance(value, list) and all(isinstance(item, str) for item in value) else []
