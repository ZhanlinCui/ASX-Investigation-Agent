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

Holdout labels remain outside the repository. Set `ASX_EVAL_HOLDOUT_ROOT` to a frozen
artifact-backed corpus:

```text
manifest.json
artifacts/
  <sha256>
<case_id>/
  bundle.json
```

The sealed manifest contains no labels, and the loader rejects serialized JSON or
recognizable label/report keys inside holdout evidence artifacts before they can
reach the reasoner. An external grader joins blind reports to labels outside this
runtime. When the root or an artifact is missing, the harness reports `NOT_RUN`; it
never converts missing holdout evidence into a pass.

The release remains recorded-only until 24 independently adjudicated point-in-time development snapshots and the 12-case sealed holdout are supplied and pass. LLM judges may be used for diagnostics, but cannot alter a hard-gate result.

## External agent execution

An external frozen-corpus run requires `GEMINI_API_KEY`,
`GEMINI_PRICING_SCHEDULE_VERSION`, `GEMINI_INPUT_AUD_PER_MILLION_TOKENS` and
`GEMINI_OUTPUT_AUD_PER_MILLION_TOKENS`. Gemini response usage is captured after
each structured call and priced into immutable artifacts tied to the deployed
model configuration. The runner never accepts a caller-supplied cost estimate:

```bash
.venv/bin/python evals/run_gold_evals.py --format markdown
```

Without a configured model, an external corpus, or immutable measured cost
artifacts, the affected external gate remains `NOT_RUN`.

## EODHD provider smoke

The isolated provider gate verifies one completed ASX session through the governed EODHD
daily-bar primary and ASX corporate-actions adapters. It does not call Gemini or create a
causal report:

```bash
.venv/bin/python evals/run_live_smoke.py --ticker BHP --trade-date 2026-08-20 --format markdown
```

Set `EODHD_API_KEY` only in the local ignored `.env` or process environment. The command
returns `NOT_RUN` when that credential is absent; a configured provider failure returns
`FAIL` with a safe provider outcome. Content-addressed response artifacts stay under the
ignored `data/live-smoke/` directory, while output contains only safe metadata and hashes.
