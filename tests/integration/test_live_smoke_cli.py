from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_live_smoke_cli_reports_not_run_without_eodhd_key() -> None:
    environment = dict(os.environ)
    environment.pop("EODHD_API_KEY", None)
    project_root = Path(__file__).resolve().parents[2]

    completed = subprocess.run(
        [
            sys.executable,
            "evals/run_live_smoke.py",
            "--ticker",
            "BHP",
            "--trade-date",
            "2026-08-20",
        ],
        cwd=project_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "NOT_RUN"
    assert payload["reason"] == "EODHD_API_KEY is not configured."
    assert "test-token" not in completed.stdout
