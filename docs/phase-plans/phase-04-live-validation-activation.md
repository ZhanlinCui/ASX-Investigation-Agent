# Phase 4: Live Validation Activation

**Status:** Activation runtime partially implemented; external execution blocked by supplied inputs
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
| P4.0 | Credential and corpus preflight | Implemented; all secrets remain outside the repository and invalid/missing inputs fail closed |
| P4.1 | Credentialed provider smoke | Blocked pending approved provider credentials and controlled ASX fixture |
| P4.2 | Development evaluation | Runtime implemented; blocked pending 24 real point-in-time cases and external execution |
| P4.3 | Sealed holdout and release decision | Independent grader reports the 12-case result and per-case failure analysis without exposing labels to runtime |

## Non-negotiable gates

- Zero lookahead, incorrect ASX-session attribution, missing material citation, invalid assertion support, provider-failure-to-no-catalyst conversion and materially wrong HIGH explanations.
- Top-1 at least 75 percent and top-2 at least 90 percent on published `EXPLAINED` cases only.
- Required abstention at 100 percent with a non-zero eligible denominator; false abstention at most 20 percent on answerable cases.
- Two equivalent runs reproduce validated decisions, assertion and artifact identities, coverage and policy trace; private model wording is not the replay contract.
- Results show raw numerators, denominators, latency, measured AUD cost, source-policy/model/pricing versions and per-case failures.

## Explicitly deferred

No alerts, portfolio features, trading execution, automatic cross-case learning, multi-user access, new data vendors or vector database are added in this phase.

## Implemented readiness boundary

The configured Gemini reasoner now captures response token usage, derives AUD cost from a versioned hash-bound pricing schedule, and emits immutable usage-cost artifacts. External evaluation rejects absent/invalid pricing before it calls the model, so a caller-supplied estimate can never become measured cost. The remaining execution gates require only external credentials, corpora and external holdout grading.

## Latest local verification

At the Phase 4 readiness checkpoint: 292 Python tests passed, Ruff and Python compile checks passed, all 24 recorded policy sentinels passed, and the six-test frontend suite plus production build passed. Development gold, sealed holdout and credentialed Live smoke remain `NOT_RUN` because this checkout has none of their external inputs.
