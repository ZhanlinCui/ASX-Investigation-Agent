# Phase 3: Causal Investigation Intelligence

**Status:** Implementation delivered in the recorded-only release candidate; Phase 3 external release gates OPEN (`NOT_RUN`)
**Branch:** `codex/phase3-causal-intelligence`
**Design:** `docs/superpowers/specs/2026-08-20-phase-3-causal-investigation-intelligence-design.md`
**Implementation plan:** `docs/superpowers/plans/2026-08-20-phase-3-causal-investigation-intelligence.md`

## Goal

Build an assertion-bound causal investigation agent for unusual ASX equity moves. The runtime remains one typed orchestrator with two bounded Gemini calls. Deterministic code owns facts, source policy, timing, claims, confidence and release gates.

## Milestones

| Milestone | Deliverable | Status |
|---|---|---|
| P3.0 | Domain contracts and synchronized documentation | Implemented; release gate OPEN |
| P3.1 | Investigation kernel and append-only decision ledger | Implemented; release gate OPEN |
| P3.2 | Exact evidence assertions, mechanism tests and deterministic claim compiler | Implemented; release gate OPEN |
| P3.3 | Shared-memory admission policy and case isolation | Implemented; release gate OPEN |
| P3.4 | Production-path frozen gold case execution | Implemented; release gate OPEN |
| P3.5 | Offline confidence calibration metadata and release gates | Implemented; release gate OPEN |
| P3.6 | Causal decision workbench and release evidence | Implemented; release gate OPEN |

## Non-negotiable rules

- Monetary values are AUD; user-facing times are AEST or AEDT on the ASX calendar.
- A material claim must be compiled from case-scoped, time-eligible evidence assertions.
- Gemini cannot fetch sources, calculate market facts, set confidence or publish material causal prose.
- The model-call limit is two structured calls. One targeted retrieval is permitted only for a structured evidence gap.
- Run and case memory are durable but case-isolated. Shared memory contains only approved policy, provider health, issuer reference facts and reviewed calibration artifacts.
- Issuer reference values are `CONTEXT_ONLY`: the raw values are not model evidence and cannot provide citations, mechanisms, causal support, directives or claims.
- Historical claims, hypotheses, model summaries, user documents and all holdout labels are prohibited shared memory.
- Real development data, sealed holdout labels and Live credentials remain external. A missing external gate is `NOT_RUN`.

## Release gates

Phase 3 cannot claim Live validation until the real development corpus, sealed holdout and credentialed Live smoke run have measured results. Safety checks use zero tolerance for lookahead, session errors, missing material citations, invalid assertion support, provider-failure misclassification and materially wrong HIGH explanations.

Behavior gates report raw numerators and denominators: top-1 at least 75 percent and top-2 at least 90 percent on published `EXPLAINED` cases only; required abstention is 100 percent with a non-zero required-case denominator; false abstention is at most 20 percent on answerable cases. Reproducibility compares validated decisions, assertion/artifact identities and policy trace; private model wording is retained only for audit and never makes an otherwise identical replay fail.

## P3.6 release record

The delivered workbench presents exact evidence assertions, mechanism tests, append-only ledger metadata and calibration sample status. Assertion links use the controlled exact-passage endpoint. The public report projection excludes case-version internals from assertions, model configuration and validation prose from ledger entries, and calibration proportions. It preserves established report fields for API compatibility.

Fresh local verification is recorded in `evals/results/phase3-evaluation.md`. The external development gold corpus, sealed holdout and credentialed Live smoke are not supplied to this checkout, so each remains `NOT_RUN`. The Phase 3 release decision stays OPEN until those gates have measured results.

## Documentation rule

`MASTER_DEVELOPMENT_PLAN.md`, this phase plan, `README.md`, `docs/product-design.md`, evaluation methodology and result files must report the same milestone state. Planned work is never described as implemented.
