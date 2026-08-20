from __future__ import annotations

from asx_investigator.domain.models import InvestigationReport


def render_markdown(report: InvestigationReport) -> str:
    """Render a readable, citation-preserving case report without adding facts."""

    lines = [
        f"# {report.ticker} investigation",
        "",
        f"**Session:** {report.trade_date.isoformat()} ({report.timezone_label})  ",
        f"**Instrument:** {report.instrument.company_name} ({report.instrument.exchange})  ",
        f"**Lifecycle:** {report.status}  ",
        f"**Outcome:** {report.outcome}",
        "",
        "## Leading assessment",
        "",
        report.assessment.summary,
        "",
    ]
    if report.market_move:
        move = report.market_move
        lines.extend(
            [
                "## Observed move",
                "",
                f"- Close-to-close: {move.close_return_pct:+.2f}%",
                f"- Opening gap: {move.open_gap_pct:+.2f}%",
                f"- Open-to-close: {move.open_to_close_pct:+.2f}%",
                f"- Turnover: AUD {move.turnover_aud:,.0f}",
                "",
            ]
        )
    lines.extend(["## Claims", ""])
    support_by_claim = {item.claim_id: item for item in report.claim_support}
    for claim in report.claims:
        citations = " ".join(f"[{item}]" for item in claim.supporting_evidence_ids)
        support = support_by_claim.get(claim.claim_id)
        support_band = support.band if support else "NOT ASSESSED"
        lines.append(
            f"- **{claim.claim_type} · support {support_band}:** "
            f"{claim.text} {citations}".rstrip()
        )
    lines.extend(
        [
            "",
            "## Confidence and coverage",
            "",
            f"- Confidence: {report.confidence.band}",
            "- Scope: selected validated hypothesis",
            f"- Calibration: {report.confidence.calibration_status}",
            f"- Confidence rules: {report.confidence.rule_version}",
            f"- Coverage: {report.coverage_status}",
            f"- Investigation completeness: {report.completeness.status}",
            (
                "- Applied caps: " + ", ".join(report.confidence.applied_caps)
                if report.confidence.applied_caps
                else "- Applied caps: none"
            ),
            "",
            "## Evidence assertions",
            "",
        ]
    )
    for assertion in report.assertions:
        eligibility = "eligible" if assertion.causal_eligible else "not eligible"
        lines.extend(
            [
                f"### [{assertion.assertion_id}] evidence [{assertion.evidence_id}]",
                "",
                f"- Span hash: `{assertion.span_hash}`",
                f"- Artifact hash: `{assertion.artifact_hash}`",
                f"- Published: {assertion.published_at.isoformat()}",
                f"- Retrieved: {assertion.retrieved_at.isoformat()}",
                f"- Authority: {assertion.source_authority}",
                f"- Role: {assertion.role}",
                f"- Causal eligibility: {eligibility}",
                f"- Mechanism hint: {assertion.mechanism_hint}",
                f"- Locator: {assertion.locator or 'Not supplied'}",
                "",
                assertion.exact_text,
                "",
            ]
        )
    lines.extend(
        [
            "## Mechanism tests",
            "",
        ]
    )
    for test in report.mechanism_tests:
        supporting = ", ".join(test.supporting_assertion_ids) or "none"
        contradicting = ", ".join(test.contradicting_assertion_ids) or "none"
        lines.extend(
            [
                f"### [{test.test_id}] {test.mechanism}: {test.status}",
                "",
                f"- Policy: {test.policy_version}",
                f"- Taxonomy: {test.taxonomy_version}",
                f"- Supporting assertions: {supporting}",
                f"- Contradicting assertions: {contradicting}",
                f"- Result: {test.summary}",
                "",
            ]
        )
    lines.extend(
        [
            "## Decision ledger",
            "",
        ]
    )
    for entry in report.ledger:
        inputs = ", ".join(f"`{item}`" for item in entry.input_hashes) or "none"
        outputs = ", ".join(f"`{item}`" for item in entry.output_hashes) or "none"
        lines.extend(
            [
                f"### {entry.sequence}. {entry.stage}: {entry.status}",
                "",
                f"- Recorded: {entry.created_at.isoformat()}",
                f"- Schema: {entry.schema_version}",
                f"- Policy: {entry.policy_version}",
                f"- Input artifact hashes: {inputs}",
                f"- Output artifact hashes: {outputs}",
                *(
                    [f"- Validation: {entry.validation_status}"]
                    if entry.validation_status is not None
                    else []
                ),
                "",
            ]
        )
    calibration = report.calibration_metadata
    calibration_rule = (
        calibration.confidence_rule_version or report.confidence.rule_version
    )
    lines.extend(
        [
            "## Calibration sample status",
            "",
            f"- Status: {calibration.status}",
            f"- Label: {calibration.label}",
            f"- Corpus: {calibration.corpus_version or 'Not attached'}",
            f"- Confidence rules: {calibration_rule}",
        ]
    )
    for band, sample in sorted(calibration.bands.items()):
        lines.append(
            f"- {band}: {sample.status}; eligible cases {sample.eligible_cases}; "
            f"material errors {sample.material_errors}"
        )
    lines.extend(
        [
            "",
            "## Evidence register",
            "",
        ]
    )
    for item in report.evidence:
        lines.extend(
            [
                f"### [{item.evidence_id}] {item.title}",
                "",
                f"- Source: [{item.source_name}]({item.source_url})",
                f"- Published: {item.published_at.isoformat()}",
                f"- Role: {item.role}",
                f"- Locator: {item.locator or 'Not supplied'}",
                "",
                item.passage,
                "",
            ]
        )
    return "\n".join(lines)
