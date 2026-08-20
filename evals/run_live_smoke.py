"""Run the opt-in EODHD ASX provider smoke gate without exposing credentials."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from asx_investigator.evaluation.live_smoke import SmokeStatus, run_eodhd_live_smoke
from asx_investigator.settings import Settings


def _markdown(payload: dict[str, object]) -> str:
    lines = ["# EODHD Live Smoke", "", f"- Status: {payload['status']}"]
    if payload["reason"]:
        lines.append(f"- Reason: {payload['reason']}")
    lines.append(f"- Ticker: {payload['ticker']}")
    lines.append(f"- ASX trade date: {payload['trade_date']}")
    return "\n".join(lines)


async def main(
    *, ticker: str, trade_date: date, artifact_dir: Path, output_format: str
) -> SmokeStatus:
    report = await run_eodhd_live_smoke(
        Settings(),
        ticker=ticker,
        trade_date=trade_date,
        artifact_dir=artifact_dir,
    )
    payload = report.model_dump(mode="json")
    print(_markdown(payload) if output_format == "markdown" else json.dumps(payload, indent=2))
    return report.status


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticker", default="BHP")
    parser.add_argument("--trade-date", required=True, type=date.fromisoformat)
    parser.add_argument("--artifact-dir", type=Path, default=Path("data/live-smoke"))
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    arguments = parser.parse_args()
    status = asyncio.run(
        main(
            ticker=arguments.ticker,
            trade_date=arguments.trade_date,
            artifact_dir=arguments.artifact_dir,
            output_format=arguments.format,
        )
    )
    if status is SmokeStatus.FAIL:
        raise SystemExit(1)
