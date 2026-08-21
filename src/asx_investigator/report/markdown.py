from __future__ import annotations

from typing import Any

from asx_investigator.domain.models import InvestigationReport
from asx_investigator.report.public import public_report_payload


def _items(payload: dict[str, Any], name: str) -> list[dict[str, Any]]:
    value = payload.get(name, [])
    return value if isinstance(value, list) else []


def render_markdown(report: InvestigationReport) -> str:
    """Render only public report metadata; passages stay endpoint-scoped."""

    public = public_report_payload(report)
    instrument = public["instrument"]
    assessment = public["assessment"]
    confidence = public["confidence"]
    completeness = public["completeness"]
    assert isinstance(instrument, dict)
    assert isinstance(assessment, dict)
    assert isinstance(confidence, dict)
    assert isinstance(completeness, dict)

    lines = [
        f"# {public['ticker']} investigation",
        "",
        f"**Session:** {public['trade_date']} ({public['timezone_label']})  ",
        f"**Instrument:** {instrument['company_name']} ({instrument['exchange']})  ",
        f"**Lifecycle:** {public['status']}  ",
        f"**Outcome:** {public['outcome']}",
        "",
        "## Leading assessment",
        "",
        str(assessment["summary"]),
        "",
    ]
    move = public["market_move"]
    if isinstance(move, dict):
        lines.extend(
            [
                "## Observed move",
                "",
                f"- Close-to-close: {float(move['close_return_pct']):+.2f}%",
                f"- Opening gap: {float(move['open_gap_pct']):+.2f}%",
                f"- Open-to-close: {float(move['open_to_close_pct']):+.2f}%",
                f"- Turnover: AUD {float(move['turnover_aud']):,.0f}",
                "",
            ]
        )
    retrieval_plan = public["retrieval_plan"]
    if isinstance(retrieval_plan, dict):
        lines.extend(
            [
                "## Investigation plan",
                "",
                f"- Retrieval policy: `{retrieval_plan['policy_version']}`",
                f"- Plan hash: `{retrieval_plan['plan_hash']}`",
                "- Evidence-gap follow-up: "
                + ("used" if retrieval_plan["follow_up_used"] else "not used"),
                "",
            ]
        )
        for lane in retrieval_plan["lanes"]:
            evidence_ids = ", ".join(f"[{item}]" for item in lane["evidence_ids"])
            detail = f"; evidence {evidence_ids}" if evidence_ids else ""
            reason = f"; reason {lane['reason_code']}" if lane["reason_code"] else ""
            lines.append(
                f"- {lane['lane']}: {lane['status']}; sources {lane['source_count']}"
                f"{detail}{reason}"
            )
        lines.append("")
    lines.extend(["## Claims", ""])
    for claim in _items(public, "claims"):
        citations = " ".join(f"[{item}]" for item in claim["supporting_evidence_ids"])
        lines.append(f"- **{claim['claim_type']}:** {claim['text']} {citations}".rstrip())
    lines.extend(
        [
            "",
            "## Confidence and coverage",
            "",
            f"- Confidence: {confidence['band']}",
            "- Scope: selected validated hypothesis",
            f"- Calibration: {confidence['calibration_status']}",
            f"- Confidence rules: {confidence['rule_version']}",
            f"- Coverage: {public['coverage_status']}",
            f"- Investigation completeness: {completeness['status']}",
            (
                "- Applied caps: " + ", ".join(confidence["applied_caps"])
                if confidence["applied_caps"]
                else "- Applied caps: none"
            ),
            "",
            "## Evidence assertions",
            "",
        ]
    )
    for assertion in _items(public, "assertions"):
        eligibility = "eligible" if assertion["causal_eligible"] else "not eligible"
        lines.extend(
            [
                f"### [{assertion['assertion_id']}] evidence [{assertion['evidence_id']}]",
                "",
                f"- Span hash: `{assertion['span_hash']}`",
                f"- Artifact hash: `{assertion['artifact_hash']}`",
                f"- Published: {assertion['published_at']}",
                f"- Retrieved: {assertion['retrieved_at']}",
                f"- Authority: {assertion['source_authority']}",
                f"- Role: {assertion['role']}",
                f"- Causal eligibility: {eligibility}",
                f"- Mechanism hint: {assertion['mechanism_hint']}",
                f"- Locator: {assertion['locator'] or 'Not supplied'}",
                f"- Exact passage: [open controlled copy]({assertion['content_endpoint']})",
                "",
            ]
        )
    lines.extend(["## Mechanism tests", ""])
    for test in _items(public, "mechanism_tests"):
        supporting = ", ".join(test["supporting_assertion_ids"]) or "none"
        contradicting = ", ".join(test["contradicting_assertion_ids"]) or "none"
        lines.extend(
            [
                f"### [{test['test_id']}] {test['mechanism']}: {test['status']}",
                "",
                f"- Policy: {test['policy_version']}",
                f"- Taxonomy: {test['taxonomy_version']}",
                f"- Supporting assertions: {supporting}",
                f"- Contradicting assertions: {contradicting}",
                f"- Result: {test['summary']}",
                "",
            ]
        )
    lines.extend(["## Decision ledger", ""])
    for entry in _items(public, "ledger"):
        inputs = ", ".join(f"`{item}`" for item in entry["input_hashes"]) or "none"
        outputs = ", ".join(f"`{item}`" for item in entry["output_hashes"]) or "none"
        lines.extend(
            [
                f"### {entry['sequence']}. {entry['stage']}: {entry['status']}",
                "",
                f"- Recorded: {entry['created_at']}",
                f"- Schema: {entry['schema_version']}",
                f"- Policy: {entry['policy_version']}",
                f"- Input artifact hashes: {inputs}",
                f"- Output artifact hashes: {outputs}",
                *(
                    [f"- Validation: {entry['validation_status']}"]
                    if entry["validation_status"] is not None
                    else []
                ),
                "",
            ]
        )
    calibration = public["calibration_metadata"]
    assert isinstance(calibration, dict)
    lines.extend(
        [
            "## Calibration sample status",
            "",
            f"- Status: {calibration['status']}",
            f"- Label: {calibration['label']}",
            f"- Corpus: {calibration['corpus_version'] or 'Not attached'}",
            "- Confidence rules: "
            f"{calibration['confidence_rule_version'] or confidence['rule_version']}",
        ]
    )
    bands = calibration["bands"]
    assert isinstance(bands, dict)
    for band, sample in sorted(bands.items()):
        assert isinstance(sample, dict)
        lines.append(
            f"- {band}: {sample['status']}; eligible cases {sample['eligible_cases']}; "
            f"material errors {sample['material_errors']}"
        )
    lines.extend(["", "## Evidence register", ""])
    for item in _items(public, "evidence"):
        source = item["source_name"]
        if item["source_host"]:
            source = f"{source} ({item['source_host']})"
        lines.extend(
            [
                f"### [{item['evidence_id']}] {item['title']}",
                "",
                f"- Source: {source}",
                f"- Published: {item['published_at']}",
                f"- Role: {item['role']}",
                f"- Content hash: `{item['content_hash']}`",
                f"- Locator: {item['locator'] or 'Not supplied'}",
                f"- Exact passage: [open controlled copy]({item['content_endpoint']})",
                "",
            ]
        )
    return "\n".join(lines)
