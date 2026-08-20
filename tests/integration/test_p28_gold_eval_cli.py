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


def test_gold_eval_cli_rejects_a_caller_supplied_model_cost_estimate() -> None:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "evals/run_gold_evals.py",
            "--format",
            "json",
            "--estimated-case-cost-aud",
            "0.01",
        ],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode != 0
    assert "unrecognized arguments: --estimated-case-cost-aud" in completed.stderr
