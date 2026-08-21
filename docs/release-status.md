# Release Status

**Candidate:** `v0.1.0-rc.1` packaging<br>
**Decision:** Release candidate; stable release not approved<br>
**As of:** 21 August 2026 AEST

## Current code state

The Phase 5 bounded retrieval planner, governed primary-source promotion, retrieval-failure abstention, operational non-causal memory routing and audited public retrieval-plan surface are implemented. The final English workbench, repository homepage and consolidated product documentation are part of the release-candidate packaging milestone.

The most recent milestone verification before final release QA reported 326 Python tests, seven frontend tests, a passing frontend production build and passing Ruff checks. The authoritative final command results are maintained in [`evals/results/final-release.md`](../evals/results/final-release.md) and will be refreshed from the final commit.

## Gate matrix

| Gate | State | Release meaning |
| --- | --- | --- |
| Local Python, lint, recorded eval, frontend lint/test/build | Packaging verification in progress | Required for release-candidate tag |
| External development gold, 24 cases | `NOT_RUN` | Stable release remains open |
| Sealed holdout, 12 cases | `NOT_RUN` | Calibration and generalization remain unapproved |
| Credentialed Live canaries | `NOT_RUN` | Live evidence path remains unapproved |

`NOT_RUN` means an external input was absent. It is not a pass, warning or inferred success.

## Inputs still required for stable release

- twenty-four adjudicated point-in-time development bundles;
- a separately controlled twelve-case blind holdout and grader;
- rotated Gemini, EODHD and discovery credentials with required provider entitlements;
- a reviewed versioned Gemini AUD pricing schedule;
- completed-session Live canaries with zero hard-safety violations.

Any credential previously pasted into chat, issue text or logs is treated as exposed and must be rotated before the Live gate.

## Repository metadata

Suggested GitHub description:

> Evidence-first Agent for investigating unusual ASX equity moves with frozen citations, bounded retrieval and calibrated-abstention gates.

Suggested topics:

`asx`, `financial-research`, `ai-agent`, `evidence`, `gemini`, `fastapi`, `react`, `evaluation`, `provenance`, `market-data`

The social preview asset is [`docs/assets/github-social-preview.png`](assets/github-social-preview.png) and is derived from a real recorded workbench run.
