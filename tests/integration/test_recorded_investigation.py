from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway


async def test_recorded_pre_open_guidance_case_produces_cited_cause() -> None:
    service = InvestigationService(tools=RecordedToolGateway.default())

    report = await service.investigate(ticker="BHP", trade_date="2026-08-20", mode="RECORDED")

    assert report.status == "COMPLETED"
    assert report.outcome == "EXPLAINED"
    assert report.assessment.primary_claim_id == "C1"
    assert report.claims[0].claim_type == "CAUSE"
    assert report.claims[0].supporting_evidence_ids
    assert report.confidence.calibration_status == "UNCALIBRATED"
    assert report.completeness.status == "COMPLETE"
    assert report.conflicts == []
