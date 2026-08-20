from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.report.markdown import render_markdown


async def test_markdown_renders_confidence_band_without_probability_percentage() -> None:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    markdown = render_markdown(report)
    confidence_section = markdown.split("## Confidence and coverage", 1)[1].split(
        "## Evidence register", 1
    )[0]

    assert "Confidence: HIGH" in confidence_section
    assert "%" not in confidence_section
    assert "Internal ordinal score" not in markdown
