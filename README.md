# ASX Investigation Agent

An evidence-led product for investigating unusual moves in ASX-listed equities. It accepts an ASX code and trading date, calculates the observed move, retrieves time-eligible evidence, and returns confidence-rated claims with citations and visible coverage limits.

The product does not recommend trades or predict prices.

## Current release

Phase 2 is in implementation. Recorded mode is available for deterministic development and evaluation. Live completion requires configured market-data and discovery providers.

Implemented foundations include ASX session handling, daily move calculations, evidence timing, citation validation, Gemini structured output, provisional confidence bands, an asynchronous API, JSON and Markdown reports, and an English research workbench.

See `MASTER_DEVELOPMENT_PLAN.md` for the roadmap and `docs/phase-plans/phase-02-evidence-complete-live-investigation.md` for the active implementation plan.

## Setup

Use Python 3.12 and pnpm.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
cd web && pnpm install
```

Required for model synthesis:

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

## Verify

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests evals
.venv/bin/python evals/run_recorded_evals.py
cd web && pnpm test && pnpm build
```

## Known limits

- Confidence is an evidence-strength band and remains `UNCALIBRATED`.
- Live announcement coverage depends on issuer sources and configured providers.
- The initial recorded corpus is a regression fixture, not proof of broad causal accuracy.
- The Phase 2 release gate remains open until durable storage, source snapshots, provider fallback and the expanded evaluation suite are complete.
