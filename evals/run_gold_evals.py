"""Report the availability and validity of external development and sealed gold corpora."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from asx_investigator.evaluation.gold import run_external_gold  # noqa: E402


async def main(output_format: str, estimated_case_cost_aud: float | None) -> None:
    reports = {
        corpus: await run_external_gold(
            corpus, estimated_cost_aud=estimated_case_cost_aud
        )
        for corpus in ("development", "holdout")
    }
    payload = {corpus: result.model_dump(mode="json") for corpus, result in reports.items()}
    if output_format == "markdown":
        print("# Gold Evaluation Availability\n")
        for corpus, result in payload.items():
            print(f"## {corpus.title()}\n\n- Status: {result['status']}")
            if result["reason"]:
                print(f"- Reason: {result['reason']}")
            for error in result["errors"]:
                print(f"- Error: {error}")
            if result["cases"]:
                print(f"- Executed bundles: {len(result['cases'])}")
    else:
        print(json.dumps(payload, indent=2))
    if any(result["status"] == "FAIL" for result in payload.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    parser.add_argument(
        "--estimated-case-cost-aud",
        type=float,
        default=None,
        help=(
            "Audited non-zero model cost per executed case in AUD. Required for an "
            "external agent release run; omission leaves that gate NOT_RUN."
        ),
    )
    arguments = parser.parse_args()
    if arguments.estimated_case_cost_aud is not None and arguments.estimated_case_cost_aud <= 0:
        parser.error("--estimated-case-cost-aud must be greater than zero")
    asyncio.run(main(arguments.format, arguments.estimated_case_cost_aud))
