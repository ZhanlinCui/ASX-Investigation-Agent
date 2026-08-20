"""Run deterministic, evidence-safety regression cases.

Usage: .venv/bin/python evals/run_recorded_evals.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from asx_investigator.domain.models import ClaimType
from asx_investigator.investigation.service import InvestigationService
from asx_investigator.providers.recorded import RecordedToolGateway

ROOT = Path(__file__).resolve().parent


async def evaluate_case(case: dict[str, str]) -> dict[str, object]:
    report = await InvestigationService(RecordedToolGateway.default()).investigate(
        case["ticker"], case["trade_date"], case["mode"]
    )
    material_claims = [
        claim
        for claim in report.claims
        if claim.claim_type in {ClaimType.CAUSE, ClaimType.CONTRIBUTOR, ClaimType.MECHANICAL}
    ]
    checks = {
        "status": str(report.status) == case["expected_status"],
        "primary_claim": report.assessment.primary_claim_id == case["expected_primary_claim_id"],
        "claim_type": bool(report.claims)
        and str(report.claims[0].claim_type) == case["expected_claim_type"],
        "all_material_claims_cited": all(
            claim.supporting_evidence_ids for claim in material_claims
        ),
        "confidence_bounded": 0 <= report.confidence.score <= 1,
        "calibration_label_visible": report.confidence.calibration_status == "UNCALIBRATED",
    }
    return {
        "name": case["name"],
        "passed": all(checks.values()),
        "checks": checks,
        "confidence": report.confidence.score,
    }


async def main() -> None:
    cases = json.loads((ROOT / "cases" / "recorded_cases.json").read_text())
    results = [await evaluate_case(case) for case in cases]
    output = {
        "passed": sum(result["passed"] for result in results),
        "total": len(results),
        "results": results,
    }
    print(json.dumps(output, indent=2))
    if output["passed"] != output["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
