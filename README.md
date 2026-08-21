# ASX Investigation Agent

An evidence-led product for investigating unusual moves in ASX-listed equities. It accepts an ASX code and trading date, calculates the observed move, retrieves time-eligible evidence, and returns confidence-rated claims with citations and visible coverage limits.

The product does not recommend trades or predict prices.

## Current release

Phase 2 and Phase 3 implementation are delivered in recorded mode. Phase 3 provides assertion-bound reasoning, deterministic mechanism tests, an append-only ledger, point-in-time shared-memory isolation, frozen gold execution, ordinal calibration gates, and audited JSON, Markdown and workbench decisions. Phase 4 has added hash-bound Gemini usage and AUD-cost readiness for external evaluation, plus a bounded EODHD provider-smoke runtime. The product is not release-approved: the external development gold corpus, sealed holdout and credentialed Live gates remain OPEN and `NOT_RUN`. P2.8 adds frozen provider artifacts, durable checkpoint recovery, bounded targeted-evidence acceptance, external gold-corpus validation and provenance display. Fresh recorded-release results are in `evals/results/phase3-evaluation.md`.

Implemented capabilities include SQLite WAL case versions and event replay, EODHD/Marketstack source policy, ASX corporate-action checks, safe PDF/text/URL ingestion, exact passage retrieval, two bounded Gemini roles, deterministic claim validation, confidence caps, JSON/Markdown reports, a persistent archive, evidence viewer, trace, refinements and CI.

See `MASTER_DEVELOPMENT_PLAN.md` for the roadmap, `docs/phase-plans/phase-05-recall-and-release-closure.md` for the active final-delivery phase, `docs/phase-plans/phase-03-causal-investigation-intelligence.md` for the recorded architecture record, and `docs/superpowers/specs/2026-08-20-phase-3-causal-investigation-intelligence-design.md` for the approved architecture.

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

Required before the full Live investigation gate can pass:

- `EODHD_API_KEY`
- `MARKETSTACK_API_KEY`
- `TAVILY_API_KEY` where discovery is enabled

Required before an external gold run can report measured model cost:

- `GEMINI_PRICING_SCHEDULE_VERSION`
- `GEMINI_INPUT_AUD_PER_MILLION_TOKENS`
- `GEMINI_OUTPUT_AUD_PER_MILLION_TOKENS`

Secrets are read by the backend only. They must not be committed or sent to the browser.

The bounded EODHD provider smoke uses only `EODHD_API_KEY`; it does not invoke Gemini,
discovery or a causal-investigation report.

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

### EODHD provider smoke

With a locally configured, ignored `.env`, run one **completed** ASX session:

```bash
.venv/bin/python evals/run_live_smoke.py --ticker BHP --trade-date 2026-08-20 --format markdown
```

The command writes raw provider snapshots only to ignored `data/live-smoke/` and emits a
safe report with provider status, coverage and artifact hashes. Missing `EODHD_API_KEY`
is `NOT_RUN`; credential, entitlement, rate-limit, schema or coverage failures are
`FAIL`. It is not an investigation result and cannot approve a Live release by itself.

## Known limits

- Confidence is a rule-governed evidence-strength band, not a probability, and remains `UNCALIBRATED`.
- Tavily results remain discovery-only; primary causal support requires frozen issuer or user-supplied official material.
- The 24 development cases are synthetic policy sentinels, not historical accuracy evidence.
- The 12-case sealed holdout is `NOT_RUN` unless `ASX_EVAL_HOLDOUT_ROOT` is supplied.
- The credentialed Live smoke gate is `NOT_RUN` in an unconfigured checkout.
- External gold execution is `NOT_RUN` unless a hash-bound Gemini usage record and versioned AUD pricing schedule are available.
- Recoverable runs resume from compatibility-checked durable stage checkpoints; incompatible checkpoints create an audited child version.
