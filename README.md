# ASX Investigator

An evidence-led agent for explaining unusual moves in ASX-listed equities. Give it an ASX code and trading date; it resolves the Sydney trading session, calculates the market signature, retrieves eligible evidence, and returns a confidence-rated explanation with traceable citations.

The product does not give trade recommendations or invent a catalyst when the evidence is weak.

## What is implemented

- A FastAPI job API with progress events, JSON result, and Markdown report.
- A calm, English-language research-workbench UI designed from the supplied warm-paper brief.
- ASX session handling in `Australia/Sydney`, including AEST/AEDT, weekend/holiday checks, and early closes.
- Deterministic EOD return, opening-gap, turnover, relative-return, and anomaly calculations, expressed in AUD.
- Evidence objects with source URL, retrieval time, content hash, source role, and locator.
- A timing gate: post-close and retrospective items cannot support a same-day causal claim.
- A claim validator: material claims cannot be released without registered supporting evidence.
- Numeric confidence scoring with visible caps for incomplete disclosure coverage, missing primary evidence, conflicts, and missing intraday data.
- Gemini structured-output synthesis (`gemini-3-flash-preview`) that receives only the evidence packet and cannot fetch, calculate, or override validation.
- Recorded BHP regression case and executable eval harness.

## Architecture

```text
Ticker + ASX date
  → session and identity resolver
  → market forensics (deterministic)
  → typed market/evidence tools
  → time-eligible evidence registry
  → Gemini constrained narrative draft
  → claim/citation validation + confidence caps
  → JSON, Markdown, and UI
```

The model is deliberately narrow. It may express a hypothesis from provided evidence, but price data, trading sessions, eligibility, confidence caps, and publication rules are deterministic code.

## Tool and source policy

| Need | Current implementation | Failure behaviour |
|---|---|---|
| ASX EOD prices | EODHD live adapter | Explicit recoverable failure; never synthetic live bars |
| Instrument identity | EODHD ASX search | Explicit unsupported/unresolved response |
| Event discovery | Tavily, optional | Empty evidence and incomplete coverage are visible |
| Issuer evidence | Issuer IR results discovered through configured search; recorded fixture for regression | No full-disclosure claim without verified coverage |
| Narrative synthesis | Gemini structured output | Omitted if unavailable or invalid; deterministic fallback remains |
| Trading session | Local ASX calendar rules | Non-trading dates return a partial result |

When sources disagree, the evidence registry preserves each item. Prices are not averaged: a provider must be selected by field policy or the run is partial. Issuer material is stronger than press reaction; evidence released after the session is context only.

## Context and memory

Each case is isolated. The model sees only a compact packet: market signature, eligible evidence excerpts, source metadata, and evidence IDs. It does not receive raw long documents or prior case narratives. Durable memory is limited to deterministic source policy, calibration artefacts, and versioned recorded fixtures—not conclusions from earlier cases.

## Run locally

Use Python 3.12.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
```

Set `GEMINI_API_KEY` in your local environment or `.env`; it is read only by the backend. `GEMINI_MODEL` defaults to `gemini-3-flash-preview`. Live market data additionally requires `EODHD_API_KEY`; event discovery is enabled by `TAVILY_API_KEY`.

```bash
.venv/bin/uvicorn asx_investigator.main:app --reload
cd web && pnpm install && pnpm dev
```

Open `http://localhost:5173`. Choose **Recorded case** with `BHP` and `2026-08-20` to run the included deterministic case without external data credentials.

## Verification and calibration

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/python evals/run_recorded_evals.py
cd web && pnpm test && pnpm build
```

The initial score is labelled `UNCALIBRATED`: it is a transparent evidence-strength score, not yet an empirical probability. Before production reliance, freeze a blind, point-in-time corpus; independently label the leading catalyst and negatives; fit a calibrator only on development cases; and report held-out citation precision, causal top-1 accuracy, abstention quality, calibration error, and coverage-failure rate.
