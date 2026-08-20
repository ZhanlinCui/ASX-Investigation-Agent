from __future__ import annotations

import math
from hashlib import sha256

from asx_investigator.confidence.calibration import RELEASE_CHECK_NAMES, CalibrationRecord
from asx_investigator.confidence.scoring import (
    ConfidenceFeatures,
    confidence_cap_maximum,
    required_confidence_caps,
)
from asx_investigator.domain.models import (
    ClaimType,
    EvidenceRole,
    InvestigationReport,
)
from asx_investigator.evaluation.models import (
    CaseEvaluation,
    EvalCaseManifest,
    GraderCheck,
    ReleaseGateReport,
)
from asx_investigator.investigation.assertions import normalized_hash
from asx_investigator.investigation.claim_compiler import (
    ClaimCompilationError,
    compile_claim,
)
from asx_investigator.market.sessions import classify_event, resolve_session

MATERIAL_CLAIMS = {ClaimType.CAUSE, ClaimType.CONTRIBUTOR, ClaimType.MECHANICAL}

# Safety checks are zero-tolerance release evidence: absence means the corpus
# has not demonstrated the property, rather than that it passed by default.
_REQUIRED_ZERO_TOLERANCE_METRICS = (
    "lookahead",
    "session",
    "citation",
    "provider_semantics",
    "reproducibility",
    "confidence_caps",
    "wrong_high",
)
_REQUIRED_ATTRIBUTION_METRICS = ("top_1", "top_2")
_CONDITIONAL_BEHAVIORAL_METRICS = ("required_abstention", "false_abstention")
_PARTIAL_DISCLOSURE_COVERAGE_STATUSES = {
    "PARTIAL_DISCLOSURE_COVERAGE",
    "SCOPED_REFINEMENT",
}


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
    confidence_caps_ok, confidence_caps_detail = _confidence_caps(report)
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
            name="confidence_caps",
            passed=confidence_caps_ok,
            detail=confidence_caps_detail,
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
        confidence_band=report.confidence.band,
        abstention_policy=manifest.abstention_policy,
    )


def evaluate_release_gates(
    records: list[CalibrationRecord],
    *,
    external_corpus_executed: bool = True,
) -> ReleaseGateReport:
    """Apply deterministic Phase 3 release rules to explicit evaluation records.

    A record is a validated external evaluation input. If that corpus did not
    execute, this function deliberately returns ``NOT_RUN`` rather than using
    local policy sentinels to manufacture a release pass.
    """

    if not external_corpus_executed or not records:
        return ReleaseGateReport(status="NOT_RUN", raw_counts={}, denominators={}, proportions={})

    safety_metrics = _REQUIRED_ZERO_TOLERANCE_METRICS[:-1]
    behavioral_metrics = (*_REQUIRED_ATTRIBUTION_METRICS, *_CONDITIONAL_BEHAVIORAL_METRICS)
    raw_counts: dict[str, dict[str, int]] = {}
    denominators: dict[str, int] = {}
    proportions: dict[str, float] = {}
    failures: list[str] = []
    for metric in (*safety_metrics, *behavioral_metrics):
        values = [record.checks[metric] for record in records if metric in record.checks]
        raw_counts[metric] = {"passed": sum(values), "failed": len(values) - sum(values)}
        denominators[metric] = len(values)
        proportions[metric] = sum(values) / len(values) if values else 0.0

    high_records = [record for record in records if record.confidence_band == "HIGH"]
    wrong_high_failures = sum(record.material_error for record in high_records)
    raw_counts["wrong_high"] = {
        "passed": len(high_records) - wrong_high_failures,
        "failed": wrong_high_failures,
    }
    denominators["wrong_high"] = len(high_records)
    proportions["wrong_high"] = (
        raw_counts["wrong_high"]["passed"] / len(high_records) if high_records else 0.0
    )

    if set(raw_counts) != RELEASE_CHECK_NAMES | {"wrong_high"}:
        raise AssertionError("Release gate metrics do not match the approved contract")
    for metric in _REQUIRED_ZERO_TOLERANCE_METRICS:
        if denominators[metric] == 0:
            failures.append(f"{metric} has no eligible observations")
            continue
        if raw_counts[metric]["failed"]:
            failures.append(f"{metric} has {raw_counts[metric]['failed']} safety failure(s)")
    for metric in _REQUIRED_ATTRIBUTION_METRICS:
        if denominators[metric] == 0:
            failures.append(f"{metric} has no eligible cases")
    if proportions["top_1"] < 0.75 and denominators["top_1"]:
        failures.append("top_1 is below the 75% threshold")
    if proportions["top_2"] < 0.90 and denominators["top_2"]:
        failures.append("top_2 is below the 90% threshold")
    if proportions["required_abstention"] < 1.0 and denominators["required_abstention"]:
        failures.append("required_abstention is below the 100% threshold")
    false_abstention_rate = 1.0 - proportions["false_abstention"]
    if false_abstention_rate > 0.20 and denominators["false_abstention"]:
        failures.append("false_abstention exceeds the 20% threshold")
    return ReleaseGateReport(
        status="FAIL" if failures else "PASS",
        raw_counts=raw_counts,
        denominators=denominators,
        proportions=proportions,
        failures=failures,
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


def _confidence_caps(report: InvestigationReport) -> tuple[bool, str]:
    """Verify declared caps against caps recomputed from report state.

    The assessment field is display metadata.  Release eligibility is derived
    afresh from selected evidence, coverage, conflicts and market resolution
    so a forged or omitted ``applied_caps`` value cannot conceal a cap.
    """

    evidence = {item.evidence_id: item for item in report.evidence}
    selected = next(
        (
            item
            for item in report.hypotheses
            if item.hypothesis_id == report.confidence.selected_hypothesis_id
        ),
        None,
    )
    selected_support = [
        evidence[evidence_id]
        for evidence_id in (selected.supporting_evidence_ids if selected else [])
        if evidence_id in evidence
    ]
    primary_authorities = {
        "PRIMARY_ISSUER",
        "APPROVED_OFFICIAL",
        "USER_SUPPLIED_OFFICIAL",
    }
    session = resolve_session(report.trade_date)
    needs_intraday_data = any(
        classify_event(item.published_at, session).session_relationship == "DURING_SESSION"
        for item in selected_support
    )
    partial_disclosure_coverage = (
        str(report.outcome) != "INCOMPLETE_DATA"
        and report.coverage_status in _PARTIAL_DISCLOSURE_COVERAGE_STATUSES
    )
    features = ConfidenceFeatures(
        source_authority=0,
        temporal_eligibility=0,
        market_signature_fit=0,
        quantitative_consistency=0,
        independent_corroboration=0,
        coverage_completeness=0,
        has_primary_evidence=any(
            item.authority in primary_authorities for item in selected_support
        ),
        disclosure_coverage_complete=not partial_disclosure_coverage,
        has_material_conflict=any(conflict.material for conflict in report.conflicts),
        timing_resolved=not needs_intraday_data,
        needs_intraday_data=needs_intraday_data,
        has_intraday_data=(
            report.market_move is not None and report.market_move.resolution == "INTRADAY"
        ),
    )
    required_caps = required_confidence_caps(features)
    declared_caps = list(report.confidence.applied_caps)
    try:
        maximum = confidence_cap_maximum(required_caps)
        confidence_cap_maximum(declared_caps)
    except ValueError as error:
        return False, str(error)
    missing = sorted(set(required_caps) - set(declared_caps))
    unexpected = sorted(set(declared_caps) - set(required_caps))
    if missing or unexpected:
        return (
            False,
            f"required_caps={required_caps}; declared_caps={declared_caps}; "
            f"missing={missing}; unexpected={unexpected}",
        )
    if report.confidence.score > maximum:
        return (
            False,
            f"score={report.confidence.score} exceeds required-cap maximum={maximum}; "
            f"required_caps={required_caps}",
        )
    return True, f"required_caps={required_caps}; maximum={maximum}"
