# Phase 3: Causal Investigation Intelligence

**Status:** Complete for the recorded-only release candidate; external evaluation and Live gates remain open
**Branch:** `codex/phase3-causal-intelligence`
**Design:** `docs/superpowers/specs/2026-08-20-phase-3-causal-investigation-intelligence-design.md`
**Implementation plan:** `docs/superpowers/plans/2026-08-20-phase-3-causal-investigation-intelligence.md`

## Goal

Build an assertion-bound causal investigation agent for unusual ASX equity moves. The runtime remains one typed orchestrator with two bounded Gemini calls. Deterministic code owns facts, source policy, timing, claims, confidence and release gates.

## Milestones

| Milestone | Deliverable | Status |
|---|---|---|
| P3.0 | Domain contracts and synchronized documentation | Complete |
| P3.1 | Investigation kernel and append-only decision ledger | Complete |
| P3.2 | Exact evidence assertions, mechanism tests and deterministic claim compiler | Complete |
| P3.3 | Shared-memory admission policy and case isolation | Complete |
| P3.4 | Production-path frozen gold case execution | Complete |
| P3.5 | Offline confidence calibration metadata and release gates | Complete |
| P3.6 | Causal decision workbench and release evidence | Complete |

## Non-negotiable rules

- Monetary values are AUD; user-facing times are AEST or AEDT on the ASX calendar.
- A material claim must be compiled from case-scoped, time-eligible evidence assertions.
- Gemini cannot fetch sources, calculate market facts, set confidence or publish material causal prose.
- The model-call limit is two structured calls. One targeted retrieval is permitted only for a structured evidence gap.
- Run and case memory are durable but case-isolated. Shared memory contains only approved policy, provider health, issuer reference facts and reviewed calibration artifacts.
- Historical claims, hypotheses, model summaries, user documents and all holdout labels are prohibited shared memory.
- Real development data, sealed holdout labels and Live credentials remain external. A missing external gate is `NOT_RUN`.

## Release gates

Phase 3 cannot claim Live validation until the real development corpus, sealed holdout and credentialed Live smoke run have measured results. Safety checks use zero tolerance for lookahead, session errors, missing material citations, invalid assertion support, provider-failure misclassification and materially wrong HIGH explanations.

Behavior gates report raw numerators and denominators: top-1 at least 75 percent, top-2 at least 90 percent, required abstention 100 percent and false abstention at most 20 percent on their eligible case sets.

## P3.6 release record

The completed workbench presents exact evidence assertions, mechanism tests, append-only ledger metadata and calibration sample status. Assertion links use the controlled exact-passage endpoint. The public report projection excludes case-version internals from assertions, model configuration and validation prose from ledger entries, and calibration proportions. It preserves established report fields for API compatibility.

Fresh local verification on 21 August 2026 passed: 244 Python tests, Ruff, the 24-case synthetic recorded suite, five frontend tests and the production frontend build. The external development gold corpus, sealed holdout and credentialed Live smoke were not supplied to this checkout, so each remains `NOT_RUN`. The detailed command record is `evals/results/phase3-evaluation.md`.

## Documentation rule

`MASTER_DEVELOPMENT_PLAN.md`, this phase plan, `README.md`, `design requirement document v1.md`, evaluation methodology and result files must report the same milestone state. Planned work is never described as implemented.
