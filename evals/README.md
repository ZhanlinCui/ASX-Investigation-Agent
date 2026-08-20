# Evaluation Harness

Run the deterministic suite from the repository root:

```bash
.venv/bin/python evals/run_recorded_evals.py
```

The command prints a fresh report without modifying tracked files and exits non-zero when an executed hard gate fails. Pass `--write-results` only when intentionally refreshing the JSON and Markdown artifacts in `evals/results/`.

## Development suite

`cases/development_suite.json` contains 24 versioned synthetic policy sentinels across disclosure, mechanical, sector, commodity, macro, multi-catalyst, ambiguous and no-catalyst classes. They exercise lifecycle outcome, top-1/top-2 attribution, grounding, temporal integrity, abstention, provider-failure semantics, confidence semantics, latency and cost.

These fixtures validate deterministic safety and orchestration. They are not evidence of historical causal accuracy and must never be reported as such.

## Sealed holdout

Holdout labels remain outside the repository. Set `ASX_EVAL_HOLDOUT_ROOT` to a directory containing:

```text
holdout.json
reports/
  <case_id>.json
```

Each report artifact contains `report`, `latency_ms` and `estimated_cost_aud`. When the root or an artifact is missing, the harness reports `NOT_RUN`; it never converts missing holdout evidence into a pass.

The release remains recorded-only until 24 independently adjudicated point-in-time development snapshots and the 12-case sealed holdout are supplied and pass. LLM judges may be used for diagnostics, but cannot alter a hard-gate result.
