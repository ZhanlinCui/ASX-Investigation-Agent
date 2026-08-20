from __future__ import annotations

import math
from hashlib import sha256

from asx_investigator.domain.models import (
    ClaimType,
    EvidenceRole,
    InvestigationReport,
)
from asx_investigator.evaluation.models import (
    CaseEvaluation,
    EvalCaseManifest,
    GraderCheck,
)
from asx_investigator.investigation.assertions import normalized_hash
from asx_investigator.investigation.claim_compiler import (
    ClaimCompilationError,
    compile_claim,
)
from asx_investigator.market.sessions import resolve_session

MATERIAL_CLAIMS = {ClaimType.CAUSE, ClaimType.CONTRIBUTOR, ClaimType.MECHANICAL}


def grade_report(
    manifest: EvalCaseManifest,
    report: InvestigationReport,
    *,
    latency_ms: int,
    estimated_cost_aud: float,
    ledger_reproducible: bool | None = None,
) -> CaseEvaluation:
    evidence = {item.evidence_id: item for item in report.evidence}
    material = [claim for claim in report.claims if claim.claim_type in MATERIAL_CLAIMS]
    cited_ids = {evidence_id for claim in material for evidence_id in claim.supporting_evidence_ids}
    leading = next((item for item in report.hypotheses if str(item.status) == "LEADING"), None)
    leading_ids = set(leading.supporting_evidence_ids) if leading else set()
    leading_label = leading.driver_label if leading else None
    top_two_labels = {item.driver_label for item in report.hypotheses[:2]}
    required = set(manifest.required_evidence_ids)
    blacklisted = set(manifest.future_evidence_blacklist)
    grounding_ok = all(
        claim.supporting_evidence_ids
        and all(evidence_id in evidence for evidence_id in claim.supporting_evidence_ids)
        for claim in material
    )
    temporal_ok = not (cited_ids & blacklisted) and all(
        evidence[evidence_id].role == EvidenceRole.CAUSAL_INPUT
        and evidence[evidence_id].published_at <= manifest.evidence_cutoff
        for evidence_id in cited_ids
        if evidence_id in evidence
    )
    expected_session = resolve_session(manifest.trade_date)
    session_ok = (
        report.trade_date == manifest.trade_date
        and report.timezone_label == expected_session.timezone_label
    )
    numeric_values = (
        [
            value
            for value in report.market_move.model_dump().values()
            if isinstance(value, int | float) and not isinstance(value, bool)
        ]
        if report.market_move
        else []
    )
    numeric_ok = all(math.isfinite(value) for value in numeric_values) and (
        report.market_move is None or report.market_move.turnover_aud >= 0
    )
    mechanical = next(
        (item for item in report.validation_results if item.kind == "CORPORATE_ACTION_CHECK"),
        None,
    )
    mechanical_ok = not manifest.mechanical_flags or (
        mechanical is not None
        and str(mechanical.status) == "PASS"
        and (
            "CHECKED_NO_EVENT" not in manifest.mechanical_flags
            or "0 corporate actions" in mechanical.summary
        )
    )
    if manifest.abstention_policy == "REQUIRED":
        abstention_ok = str(report.outcome) in {
            "INSUFFICIENT_EVIDENCE",
            "INCOMPLETE_DATA",
            "NO_IDENTIFIABLE_CATALYST",
        }
    elif manifest.abstention_policy == "FORBIDDEN":
        abstention_ok = str(report.outcome) == "EXPLAINED"
    else:
        abstention_ok = True
    top_one_ok = str(report.outcome) != "EXPLAINED" or (
        (not required or bool(required & leading_ids)) and leading_label in manifest.driver_labels
    )
    top_two_ok = bool(
        top_two_labels & set([*manifest.driver_labels, *manifest.acceptable_alternatives])
    )
    provider_semantics_ok = not (
        any(gap.capability == "market_data" for gap in report.coverage_gaps)
        and str(report.outcome) == "NO_IDENTIFIABLE_CATALYST"
    )
    assertion_integrity_ok, assertion_detail = _assertion_integrity(report, material)
    claim_compilation_ok, compilation_detail = _claim_compilation(report, material)
    calibration_ok, calibration_detail = _calibration_metadata(report)
    checks = [
        GraderCheck(
            name="expected_outcome",
            passed=str(report.outcome) == manifest.expected_outcome,
            detail=f"observed={report.outcome}; expected={manifest.expected_outcome}",
        ),
        GraderCheck(
            name="top_1_attribution",
            passed=top_one_ok,
            detail=(
                f"label={leading_label}; leading={sorted(leading_ids)}; required={sorted(required)}"
            ),
        ),
        GraderCheck(
            name="top_2_attribution",
            passed=top_two_ok if str(report.outcome) == "EXPLAINED" else True,
            detail=f"top_two_labels={sorted(top_two_labels)}",
        ),
        GraderCheck(
            name="grounding",
            passed=grounding_ok,
            detail=f"material_claims={len(material)}; cited_ids={sorted(cited_ids)}",
        ),
        GraderCheck(
            name="temporal_integrity",
            passed=temporal_ok,
            detail=f"blacklisted_citations={sorted(cited_ids & blacklisted)}",
        ),
        GraderCheck(
            name="session_integrity",
            passed=session_ok,
            detail=(
                f"trade_date={report.trade_date}; timezone={report.timezone_label}; "
                f"expected_timezone={expected_session.timezone_label}"
            ),
        ),
        GraderCheck(
            name="numeric_integrity",
            passed=numeric_ok,
            detail=f"finite_values={numeric_ok}; values_checked={len(numeric_values)}",
        ),
        GraderCheck(
            name="mechanical_flags",
            passed=mechanical_ok,
            detail=f"expected={manifest.mechanical_flags}; validation={mechanical}",
        ),
        GraderCheck(
            name="abstention",
            passed=abstention_ok,
            detail=f"policy={manifest.abstention_policy}; outcome={report.outcome}",
        ),
        GraderCheck(
            name="coverage",
            passed=report.coverage_status == manifest.coverage_expectation,
            detail=(f"observed={report.coverage_status}; expected={manifest.coverage_expectation}"),
        ),
        GraderCheck(
            name="provider_failure_semantics",
            passed=provider_semantics_ok,
            detail="Provider failure must not be rendered as no identifiable catalyst.",
        ),
        GraderCheck(
            name="confidence_semantics",
            passed=(
                report.confidence.band in {"LOW", "MEDIUM", "HIGH"}
                and report.confidence.score_interpretation == "INTERNAL_ORDINAL_NOT_PROBABILITY"
            ),
            detail=f"band={report.confidence.band}",
        ),
        GraderCheck(
            name="assertion_integrity",
            passed=assertion_integrity_ok,
            detail=assertion_detail,
        ),
        GraderCheck(
            name="claim_compilation",
            passed=claim_compilation_ok,
            detail=compilation_detail,
        ),
        GraderCheck(
            name="ledger_reproducibility",
            passed=ledger_reproducible is not False,
            detail=(
                "Two production-path runs had matching normalized ledgers."
                if ledger_reproducible is True
                else "Not independently executed at this direct report-grading boundary."
                if ledger_reproducible is None
                else "Two production-path runs produced different normalized ledgers."
            ),
            hard_gate=ledger_reproducible is not None,
        ),
        GraderCheck(
            name="calibration_metadata",
            passed=calibration_ok,
            detail=calibration_detail,
        ),
        GraderCheck(
            name="latency",
            passed=latency_ms <= manifest.max_latency_ms,
            detail=f"observed_ms={latency_ms}; max_ms={manifest.max_latency_ms}",
        ),
        GraderCheck(
            name="cost",
            passed=estimated_cost_aud <= manifest.max_cost_aud,
            detail=(f"observed_aud={estimated_cost_aud:.6f}; max_aud={manifest.max_cost_aud:.6f}"),
        ),
    ]
    passed_count = sum(check.passed for check in checks)
    return CaseEvaluation(
        case_id=manifest.case_id,
        passed=all(check.passed for check in checks if check.hard_gate),
        checks=checks,
        raw_counts={"passed": passed_count, "failed": len(checks) - passed_count},
        latency_ms=latency_ms,
        estimated_cost_aud=estimated_cost_aud,
    )


def normalized_ledger(report: InvestigationReport) -> list[dict[str, object]]:
    """Compare replay-safe ledger fields without process-clock timestamps."""

    return [
        {
            "sequence": entry.sequence,
            "stage": entry.stage,
            "status": entry.status,
            "input_hashes": entry.input_hashes,
            "output_hashes": entry.output_hashes,
            "schema_version": entry.schema_version,
            "policy_version": entry.policy_version,
            "model_configuration": entry.model_configuration,
            "validation_status": entry.validation_status,
            "validation_summary": entry.validation_summary,
        }
        for entry in report.ledger
    ]


def _assertion_integrity(report: InvestigationReport, material: list[object]) -> tuple[bool, str]:
    evidence = {item.evidence_id: item for item in report.evidence}
    assertions_by_evidence = {
        item.evidence_id: item for item in report.assertions if item.causal_eligible
    }
    failures: list[str] = []
    for claim in material:
        supporting_ids = getattr(claim, "supporting_evidence_ids", [])
        if not supporting_ids:
            failures.append(f"{claim.claim_id}: no supporting evidence")
            continue
        for evidence_id in supporting_ids:
            evidence_item = evidence.get(evidence_id)
            assertion = assertions_by_evidence.get(evidence_id)
            if evidence_item is None or assertion is None:
                failures.append(f"{claim.claim_id}: missing eligible assertion for {evidence_id}")
                continue
            expected_span_hash = sha256(evidence_item.passage[:1_800].encode("utf-8")).hexdigest()
            if (
                assertion.span_hash != expected_span_hash
                or assertion.exact_text != evidence_item.passage[:1_800]
                or assertion.artifact_hash != normalized_hash(evidence_item.content_hash)
            ):
                failures.append(f"{claim.claim_id}: invalid assertion span for {evidence_id}")
    return (
        not failures,
        "All material citations resolve to eligible, hash-bound assertions."
        if not failures
        else "; ".join(failures),
    )


def _claim_compilation(report: InvestigationReport, material: list[object]) -> tuple[bool, str]:
    assertions_by_evidence = {
        item.evidence_id: item for item in report.assertions if item.causal_eligible
    }
    for claim in material:
        if getattr(claim, "claim_type", None) != ClaimType.CAUSE:
            continue
        supporting = [
            assertions_by_evidence[evidence_id]
            for evidence_id in claim.supporting_evidence_ids
            if evidence_id in assertions_by_evidence
        ]
        if len(supporting) != len(claim.supporting_evidence_ids) or not supporting:
            return False, f"{claim.claim_id}: citations cannot be compiled from assertions"
        try:
            compiled = compile_claim(
                ticker=report.ticker,
                mechanism=supporting[0].mechanism_hint,
                assertions=supporting,
            )
        except ClaimCompilationError as error:
            return False, f"{claim.claim_id}: {error}"
        if (
            compiled.text != claim.text
            or compiled.supporting_evidence_ids != claim.supporting_evidence_ids
        ):
            return False, f"{claim.claim_id}: does not match deterministic compilation"
    return True, "Material cause claims match deterministic assertion compilation."


def _calibration_metadata(report: InvestigationReport) -> tuple[bool, str]:
    try:
        report.calibration_metadata.__class__.model_validate(
            report.calibration_metadata.model_dump(mode="json")
        )
    except ValueError as error:
        return False, f"Invalid calibration metadata: {error}"
    return True, f"Calibration metadata status={report.calibration_metadata.status}."
