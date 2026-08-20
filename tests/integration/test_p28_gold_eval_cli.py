import json
import subprocess
import sys
from pathlib import Path


def test_gold_eval_cli_reports_not_run_without_external_corpus() -> None:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "evals/run_gold_evals.py", "--format", "json"],
        cwd=root,
        capture_output=True,
        check=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload["holdout"]["status"] == "NOT_RUN"
