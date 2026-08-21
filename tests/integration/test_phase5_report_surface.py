import json

from asx_investigator.domain.models import InvestigationReport
from asx_investigator.investigation.planning import DriverLane
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway
from asx_investigator.report.markdown import render_markdown
from asx_investigator.report.public import public_report_payload


async def test_completed_report_publishes_a_safe_seven_lane_retrieval_summary() -> None:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    assert report.retrieval_plan is not None
    assert report.retrieval_plan.policy_version == "retrieval-policy-v1"
    assert len(report.retrieval_plan.plan_hash) == 64
    assert {lane.lane for lane in report.retrieval_plan.lanes} == {
        item.value for item in DriverLane
    }
    assert all(lane.status != "PLANNED" for lane in report.retrieval_plan.lanes)

    public = public_report_payload(report)
    serialized = json.dumps(public)
    retrieval = public["retrieval_plan"]
    assert set(retrieval) == {
        "policy_version",
        "plan_hash",
        "follow_up_used",
        "lanes",
    }
    assert set(retrieval["lanes"][0]) == {
        "lane",
        "status",
        "evidence_ids",
        "source_count",
        "reason_code",
    }
    assert "ASX announcement" not in serialized
    assert "query" not in serialized.lower()
    assert "context_facts" not in serialized

    markdown = render_markdown(report)
    assert "## Investigation plan" in markdown
    assert "Retrieval policy: `retrieval-policy-v1`" in markdown
    assert "ASX announcement" not in markdown


async def test_report_contract_remains_compatible_without_retrieval_summary() -> None:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )
    legacy = report.model_dump(mode="json")
    legacy.pop("retrieval_plan")

    parsed = InvestigationReport.model_validate(legacy)

    assert parsed.retrieval_plan is None
    assert public_report_payload(parsed)["retrieval_plan"] is None
    assert "## Investigation plan" not in render_markdown(parsed)
