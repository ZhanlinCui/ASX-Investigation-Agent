# Phase 2: Evidence-Complete Live Investigation

**Status:** Recorded release candidate; external Live gates open

**Branch:** `phase2/evidence-complete-live`  
**Model:** `gemini-3-flash-preview`, configurable through `GEMINI_MODEL`

## Goal

Turn the Phase 1 recorded vertical slice into a durable, evidence-complete investigation product that can run configured live cases, explain its gaps, and pass a point-in-time evaluation suite.

## Architectural decision

The runtime is one typed state machine:

```text
request
  -> resolve instrument and ASX session
  -> acquire and reconcile market data
  -> test mechanical explanations
  -> discover, freeze and retrieve evidence
  -> generate ranked hypotheses
  -> perform at most one targeted retrieval
  -> challenge the leading hypothesis
  -> run deterministic validation
  -> apply confidence caps and abstention
  -> persist and publish one report state
```

Gemini receives a bounded evidence packet and returns structured hypotheses. It cannot fetch data, calculate a market fact, assign confidence or cite an unknown evidence ID. Deterministic code remains authoritative for timing, calculations, citations, coverage and release decisions.

## Global constraints

- Monetary output is AUD.
- User-facing time is AEST or AEDT through `Australia/Sydney`.
- Completed case versions and evidence artifacts are immutable.
- Provider failure and a successful empty response are distinct states.
- Post-move evidence cannot support an earlier causal claim.
- A model failure results in `INSUFFICIENT_EVIDENCE`, not a heuristic cause.
- The live historical window is 12 months unless point-in-time source coverage proves otherwise.
- No ASX page scraping, automatic cross-case learning, authentication or trading features.

## Milestone checklist

### P2.0: Contracts and documentation

- [x] Add investigation lifecycle and outcome as separate enums.
- [x] Add provider outcomes, hypotheses, validations, gaps, conflicts, completeness and trace references to the domain contract.
- [x] Keep existing report fields readable while adding Phase 2 fields.
- [x] Align the master plan, product requirements, README and API schema.
- [x] Gate: schema round-trip and backward-compatibility tests pass.

### P2.1: Durable case memory

- [x] Create SQLite WAL schema for cases, versions, events, provider calls and evidence indexes.
- [x] Store report and request payloads as schema-versioned JSON.
- [x] Make event sequence append-only and replayable from a sequence number.
- [x] Requeue recoverable runs at application startup.
- [x] Add child versions for typed refinements; never update a completed version in place.
- [x] Store raw bytes in a SHA-256 content-addressed artifact directory.
- [x] Gate: restart, event replay, version lineage, immutability and artifact deduplication tests pass.

### P2.2: Live market truth

- [x] Wrap EODHD and Marketstack in the same typed market-data interface.
- [x] Use EODHD when complete; use Marketstack only on empty, partial or failed primary coverage.
- [x] Compare sources when both are available. Record OHLC differences above 0.5% and volume differences above 5%.
- [x] Preserve selected source, rejected values and conflict reason.
- [x] Add corporate-action and benchmark-context interfaces without inferring unavailable values.
- [x] Gate: provider contract, fallback, disagreement and live-window tests pass.

### P2.3: Evidence and context

- [x] Accept PDF and text up to 20 MB and safe HTTP/HTTPS URLs.
- [x] Reject private/reserved hosts, excessive redirects, unsupported MIME types and oversized responses.
- [x] Freeze content before parsing; persist source metadata and hash.
- [x] Extract page-aware PDF passages and block-aware HTML/text passages.
- [x] Deduplicate identical content and group shared origins.
- [x] Index passages with SQLite FTS5 and filter by case version, role, authority and publication cutoff.
- [x] Assemble at most 12 snippets of at most 1,800 characters each.
- [x] Gate: exact locator, temporal eligibility, injection isolation, deduplication and context-budget tests pass.

### P2.4: Controlled investigation

- [x] Persist stage checkpoints and explicit transition events.
- [x] First model role returns up to five ranked, materially different hypotheses.
- [x] One targeted retrieval is allowed only when a structured evidence gap names its purpose and query.
- [x] Second model role challenges the leading hypothesis and returns stronger alternatives or violations.
- [x] Reject unknown evidence IDs and unsupported material claims.
- [x] Separate lifecycle from `EXPLAINED`, `NO_IDENTIFIABLE_CATALYST`, `INSUFFICIENT_EVIDENCE` and `INCOMPLETE_DATA`.
- [x] Gate: recorded, after-close, conflicting-source, no-catalyst and model-failure cases terminate correctly.

### P2.5: Confidence and abstention

- [x] Store claim support, selected-hypothesis strength and investigation completeness separately.
- [x] Compute bands from source authority, timing, market fit, corroboration, conflict, alternatives and coverage.
- [x] Apply explicit caps for missing primary evidence, incomplete disclosure coverage, material conflict and missing timing resolution.
- [x] Render the band and cap reasons; do not describe the internal score as probability.
- [x] Gate: monotonic feature, cap and abstention tests pass.

### P2.6: Evaluation

- [x] Define a versioned case-manifest schema and deterministic grader result schema.
- [x] Build 24 synthetic development policy sentinels across disclosure, mechanical, sector, commodity, macro, multi-catalyst, ambiguous and no-catalyst classes.
- [x] Keep exactly 12 holdout labels outside the repository and load them from `ASX_EVAL_HOLDOUT_ROOT`.
- [x] Add provider, temporal, grounding, top-1/top-2 attribution, abstention, latency and cost graders.
- [x] Publish JSON and Markdown reports with raw counts and per-case failures.
- [ ] Freeze and adjudicate 24 real point-in-time development cases; synthetic sentinels are not accuracy evidence.
- [ ] Gate: sealed holdout and credentialed live gates remain `NOT_RUN`; neither is reported as passed.

### P2.7: Workbench and release

- [x] Add case archive, persisted running stages and retry controls.
- [x] Add hypotheses, evidence passage viewer, gaps, conflicts, caps, completeness and trace.
- [x] Add typed refinement and parent-child version comparison.
- [x] Keep JSON, Markdown and UI on the same report schema.
- [x] Add CI for Python tests/lint, frontend tests/build and recorded evaluation smoke.
- [ ] Gate: clean checkout verification and credentialed live smoke pass, or the release remains recorded-only.

## Public API additions

- `GET /api/v1/investigations`
- `POST /api/v1/investigations/{case_id}/versions`
- `POST /api/v1/investigations/{case_id}/retry`
- `POST /api/v1/sources/upload`
- `POST /api/v1/sources/fetch`
- `GET /api/v1/evidence/{evidence_id}/content?version_id={version_id}` for case-scoped evidence; globally unique uploaded-source IDs may omit the query parameter

Existing create, get, events, JSON and Markdown behaviour remains available. SSE events have a monotonically increasing sequence and can replay from `after_sequence` or the standard `Last-Event-ID` header.

## Completion evidence

The Phase 2 release record must contain the code commit, source-policy version, model configuration, provider mode, full test output, evaluation report, known limitations and live-gate status.
