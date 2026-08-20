from __future__ import annotations

import json
import os
from pathlib import Path

from asx_investigator.evaluation.models import EvalSuiteManifest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEVELOPMENT_MANIFEST = PROJECT_ROOT / "evals" / "cases" / "development_suite.json"


class HoldoutUnavailable(RuntimeError):
    """Sealed labels are intentionally unavailable to production code and normal runs."""


def _load_suite(path: Path) -> EvalSuiteManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    defaults = payload.pop("defaults", {})
    payload["cases"] = [{**defaults, **case} for case in payload.get("cases", [])]
    return EvalSuiteManifest.model_validate(payload)


def load_development_suite() -> EvalSuiteManifest:
    return _load_suite(DEVELOPMENT_MANIFEST)


def load_holdout_suite() -> EvalSuiteManifest:
    root = os.environ.get("ASX_EVAL_HOLDOUT_ROOT")
    if not root:
        raise HoldoutUnavailable("ASX_EVAL_HOLDOUT_ROOT is not configured")
    path = Path(root) / "holdout.json"
    if not path.is_file():
        raise HoldoutUnavailable(f"Sealed holdout manifest is missing: {path}")
    suite = _load_suite(path)
    if len(suite.cases) != 12:
        raise HoldoutUnavailable(
            f"Sealed holdout must contain exactly 12 cases; found {len(suite.cases)}"
        )
    return suite
