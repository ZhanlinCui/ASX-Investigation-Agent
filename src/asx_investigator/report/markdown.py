from __future__ import annotations

from asx_investigator.domain.models import InvestigationReport


def render_markdown(report: InvestigationReport) -> str:
    """Render a readable, citation-preserving case report without adding facts."""

    lines = [
        f"# {report.ticker} investigation",
        "",
        f"**Session:** {report.trade_date.isoformat()} ({report.timezone_label})  ",
        f"**Instrument:** {report.instrument.company_name} ({report.instrument.exchange})  ",
        f"**Status:** {report.status}",
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
                f"- Turnover: A${move.turnover_aud:,.0f}",
                "",
            ]
        )
    lines.extend(["## Claims", ""])
    for claim in report.claims:
        citations = " ".join(f"[{item}]" for item in claim.supporting_evidence_ids)
        confidence = "—" if claim.confidence is None else f"{claim.confidence:.0%}"
        lines.append(f"- **{claim.claim_type} · {confidence}:** {claim.text} {citations}".rstrip())
    lines.extend(
        [
            "",
            "## Confidence and coverage",
            "",
            f"- Confidence: {report.confidence.band} ({report.confidence.score:.0%})",
            f"- Calibration: {report.confidence.calibration_status}",
            f"- Coverage: {report.coverage_status}",
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
