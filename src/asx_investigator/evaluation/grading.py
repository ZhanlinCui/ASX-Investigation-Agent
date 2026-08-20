from __future__ import annotations

from asx_investigator.domain.models import ClaimType, EvidenceRole, InvestigationReport
from asx_investigator.evaluation.models import (
    CaseEvaluation,
    EvalCaseManifest,
    GraderCheck,
)

MATERIAL_CLAIMS = {ClaimType.CAUSE, ClaimType.CONTRIBUTOR, ClaimType.MECHANICAL}


def grade_report(
    manifest: EvalCaseManifest,
    report: InvestigationReport,
    *,
    latency_ms: int,
    estimated_cost_aud: float,
) -> CaseEvaluation:
    evidence = {item.evidence_id: item for item in report.evidence}
    material = [claim for claim in report.claims if claim.claim_type in MATERIAL_CLAIMS]
    cited_ids = {
        evidence_id for claim in material for evidence_id in claim.supporting_evidence_ids
    }
    leading = next(
        (item for item in report.hypotheses if str(item.status) == "LEADING"), None
    )
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
        for evidence_id in cited_ids
        if evidence_id in evidence
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
        (not required or bool(required & leading_ids))
        and leading_label in manifest.driver_labels
    )
    top_two_ok = bool(
        top_two_labels
        & set([*manifest.driver_labels, *manifest.acceptable_alternatives])
    )
    provider_semantics_ok = not (
        any(gap.capability == "market_data" for gap in report.coverage_gaps)
        and str(report.outcome) == "NO_IDENTIFIABLE_CATALYST"
    )
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
                f"label={leading_label}; leading={sorted(leading_ids)}; "
                f"required={sorted(required)}"
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
            name="abstention",
            passed=abstention_ok,
            detail=f"policy={manifest.abstention_policy}; outcome={report.outcome}",
        ),
        GraderCheck(
            name="coverage",
            passed=report.coverage_status == manifest.coverage_expectation,
            detail=(
                f"observed={report.coverage_status}; "
                f"expected={manifest.coverage_expectation}"
            ),
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
                and report.confidence.score_interpretation
                == "INTERNAL_ORDINAL_NOT_PROBABILITY"
            ),
            detail=f"band={report.confidence.band}",
        ),
        GraderCheck(
            name="latency",
            passed=latency_ms <= manifest.max_latency_ms,
            detail=f"observed_ms={latency_ms}; max_ms={manifest.max_latency_ms}",
        ),
        GraderCheck(
            name="cost",
            passed=estimated_cost_aud <= manifest.max_cost_aud,
            detail=(
                f"observed_aud={estimated_cost_aud:.6f}; "
                f"max_aud={manifest.max_cost_aud:.6f}"
            ),
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
