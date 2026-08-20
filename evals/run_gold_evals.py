"""Report the availability and validity of external development and sealed gold corpora."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from asx_investigator.evaluation.gold import load_gold_corpus  # noqa: E402


def main() -> None:
    payload = {
        corpus: load_gold_corpus(corpus).model_dump(mode="json")
        for corpus in ("development", "holdout")
    }
    print(json.dumps(payload, indent=2))
    if any(result["status"] == "FAIL" for result in payload.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=["json"], default="json")
    parser.parse_args()
    main()
