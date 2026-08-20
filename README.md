# ASX Investigation Agent

An evidence-led product for investigating unusual moves in ASX-listed equities. It accepts an ASX code and trading date, calculates the observed move, retrieves time-eligible evidence, and returns confidence-rated claims with citations and visible coverage limits.

The product does not recommend trades or predict prices.

## Current release

Phase 2 product implementation is complete in recorded mode. Phase 3 is complete: P3.0–P3.2 establish assertion-bound reasoning, mechanism tests and an append-only ledger; P3.3 isolates point-in-time shared memory; P3.4 executes frozen gold bundles through the production path; P3.5 adds ordinal calibration metadata and release gates; and P3.6 exposes audited causal decisions in JSON, Markdown and the workbench. P2.8 adds frozen provider artifacts, durable checkpoint recovery, bounded targeted-evidence acceptance, external gold-corpus validation and provenance display. Live completion remains gated by provider credentials and independently adjudicated point-in-time evaluation data. Fresh recorded-release results are in `evals/results/phase3-evaluation.md`.

Implemented capabilities include SQLite WAL case versions and event replay, EODHD/Marketstack source policy, ASX corporate-action checks, safe PDF/text/URL ingestion, exact passage retrieval, two bounded Gemini roles, deterministic claim validation, confidence caps, JSON/Markdown reports, a persistent archive, evidence viewer, trace, refinements and CI.

See `MASTER_DEVELOPMENT_PLAN.md` for the roadmap, `docs/phase-plans/phase-03-causal-investigation-intelligence.md` for the active phase record, and `docs/superpowers/specs/2026-08-20-phase-3-causal-investigation-intelligence-design.md` for the approved architecture.

## Setup

Use Python 3.12 and pnpm.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
cd web && pnpm install
```

Required for Live model synthesis:

- `GEMINI_API_KEY`
- `GEMINI_MODEL`, default `gemini-3-flash-preview`

Required before the Live gate can pass:

- `EODHD_API_KEY`
- `MARKETSTACK_API_KEY`
- `TAVILY_API_KEY` where discovery is enabled

Secrets are read by the backend only. They must not be committed or sent to the browser.

## Run

```bash
.venv/bin/uvicorn asx_investigator.main:app --reload
cd web && pnpm dev
```

Open `http://localhost:5173`. The recorded BHP case uses ticker `BHP`, date `2026-08-20`, and mode `RECORDED`.

The workbench can attach PDF, HTML or text sources up to 20 MB. URL ingestion is available through `POST /api/v1/sources/fetch`; private and reserved network targets are rejected.

## Verify

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests evals
.venv/bin/python evals/run_recorded_evals.py
.venv/bin/python evals/run_gold_evals.py --format markdown
cd web && pnpm test && pnpm build
```

Use `evals/run_recorded_evals.py --write-results` only when intentionally refreshing the versioned evaluation artifacts.

## Known limits

- Confidence is a rule-governed evidence-strength band, not a probability, and remains `UNCALIBRATED`.
- Tavily results remain discovery-only; primary causal support requires frozen issuer or user-supplied official material.
- The 24 development cases are synthetic policy sentinels, not historical accuracy evidence.
- The 12-case sealed holdout is `NOT_RUN` unless `ASX_EVAL_HOLDOUT_ROOT` is supplied.
- The credentialed Live smoke gate is `NOT_RUN` in an unconfigured checkout.
- Recoverable runs resume from compatibility-checked durable stage checkpoints; incompatible checkpoints create an audited child version.
