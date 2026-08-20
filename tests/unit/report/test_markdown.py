from datetime import UTC, datetime

from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.report.markdown import render_markdown
from asx_investigator.report.public import public_report_payload


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


async def test_public_report_converts_all_visible_timestamps_to_sydney_time() -> None:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )
    utc_published_at = datetime(2026, 8, 19, 22, 30, tzinfo=UTC)
    utc_retrieved_at = datetime(2026, 8, 20, 6, 30, tzinfo=UTC)
    utc_evidence = report.evidence[0].model_copy(
        update={
            "published_at": utc_published_at,
            "retrieved_at": utc_retrieved_at,
        }
    )
    utc_assertion = report.assertions[0].model_copy(
        update={
            "published_at": utc_evidence.published_at,
            "retrieved_at": utc_evidence.retrieved_at,
        }
    )
    public = public_report_payload(
        report.model_copy(update={"evidence": [utc_evidence], "assertions": [utc_assertion]})
    )

    assert public["evidence"][0]["published_at"].endswith("+10:00")
    assert public["evidence"][0]["retrieved_at"].endswith("+10:00")
    assert public["assertions"][0]["published_at"].endswith("+10:00")
    assert public["assertions"][0]["retrieved_at"].endswith("+10:00")
    assert all(not value.endswith("+00:00") for value in [
        public["mechanism_tests"][0]["created_at"],
        public["ledger"][0]["created_at"],
    ])
