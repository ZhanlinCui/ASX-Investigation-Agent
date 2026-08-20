# Phase 4: Live Validation Activation

**Status:** Blocked by external inputs; no product-scope expansion is authorized
**Prerequisite implementation:** Phase 3 recorded-release candidate
**Detailed runbook:** `docs/superpowers/plans/2026-08-21-phase-4-live-validation-activation.md`

## Goal

Turn the recorded-release candidate into a measured release candidate by running the existing governed Live providers and external evaluation gates. This phase changes neither the causal-agent architecture nor the memory policy.

## Required external inputs

- Credentials for the approved market, discovery and Gemini providers, supplied only through runtime environment variables.
- A 24-case adjudicated development corpus at `ASX_EVAL_DEVELOPMENT_ROOT`.
- A separately controlled 12-case sealed holdout corpus and external grader at `ASX_EVAL_HOLDOUT_ROOT`.
- An approved versioned AUD model-pricing schedule and captured model-usage records. A CLI estimate is not measured cost evidence.

## Milestones

| Milestone | Deliverable | Gate |
|---|---|---|
| P4.0 | Credential and corpus preflight | All secrets remain outside the repository; corpus admission is valid and labels remain sealed |
| P4.1 | Credentialed provider smoke | Approved providers return auditable outcomes for a controlled ASX session; provider failures remain explicit |
| P4.2 | Development evaluation | 24 real point-in-time cases execute through the deployed structured-reasoner path with measured AUD cost, latency and raw counts |
| P4.3 | Sealed holdout and release decision | Independent grader reports the 12-case result and per-case failure analysis without exposing labels to runtime |

## Non-negotiable gates

- Zero lookahead, incorrect ASX-session attribution, missing material citation, invalid assertion support, provider-failure-to-no-catalyst conversion and materially wrong HIGH explanations.
- Top-1 at least 75 percent and top-2 at least 90 percent on published `EXPLAINED` cases only.
- Required abstention at 100 percent with a non-zero eligible denominator; false abstention at most 20 percent on answerable cases.
- Two equivalent runs reproduce validated decisions, assertion and artifact identities, coverage and policy trace; private model wording is not the replay contract.
- Results show raw numerators, denominators, latency, measured AUD cost, source-policy/model/pricing versions and per-case failures.

## Explicitly deferred

No alerts, portfolio features, trading execution, automatic cross-case learning, multi-user access, new data vendors or vector database are added in this phase.
