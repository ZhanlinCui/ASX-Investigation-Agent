# Phase 5: Recall and Release Closure

**Status:** Planned; implementation not started
**Prerequisite:** Phase 4 runtime readiness is implemented; external Phase 4 gates remain `NOT_RUN`
**Detailed implementation plan:** `docs/superpowers/plans/2026-08-21-final-delivery-closure.md`

## Goal

Close the remaining gap between the recorded release candidate and a genuinely deliverable ASX investigation product. Phase 5 increases Live evidence recall, operationalises the already safe memory boundaries, and produces real external evaluation evidence. It does not replace the controlled investigation kernel with an open-ended agent or add unrelated product scope.

## Objective architecture assessment

The current product is not the five-node DAG described in an older review. It has an eleven-stage durable investigation state machine, bounded ranked-hypothesis generation, one evidence-gap retrieval opportunity, an independent challenge call, deterministic validation, claim compilation, confidence caps and abstention. The model cannot call providers, calculate market facts, mint evidence IDs or publish confidence.

The review is correct about the main remaining exposure: Live discovery begins with a narrow announcement query, targeted retrieval uses the same discovery channel, and discovery-only results cannot normally become primary causal evidence. The system is consequently safe but under-recalling on issuer, sector, index-rebalance, commodity, macro, capital-markets and analyst-event cases. Shared memory is strongly isolated but not yet populated or used as an operational routing input. Evaluation integrity is strong, but the local 24-case suite is a synthetic policy sentinel rather than evidence of real causal accuracy; the 24-case development corpus and 12-case sealed holdout remain external and `NOT_RUN`.

## Product boundaries

- Retain one typed investigation kernel, two structured Gemini calls and at most one gap-directed retrieval round.
- Add deterministic tool planning and bounded parallel source lanes; do not give Gemini unrestricted provider access.
- Search remains discovery only. A causal assertion requires a frozen approved source, exact passage, eligible timestamp and deterministic authority classification.
- Shared memory may route retrieval and provider selection. It may not support a causal claim or carry a prior case conclusion.
- Confidence remains `LOW`, `MEDIUM` or `HIGH`; no probability language is introduced.
- No vector database, general multi-agent framework, plugin marketplace, alerts, portfolio features, trade recommendations or automatic cross-case learning.

## Milestones

| Milestone | Deliverable | Exit gate |
|---|---|---|
| P5.0 | Contract and documentation reset | Current implementation, open gates and Phase 5 scope agree across the master plan, product requirement and phase plan |
| P5.1 | Deterministic retrieval planner | Every investigation creates a bounded, inspectable plan across applicable driver lanes; provider/model budgets and stop conditions are tested |
| P5.2 | Primary-source acquisition and coverage | Approved official documents are securely frozen, timestamped, passage-indexed and promoted by policy; discovery results alone remain non-causal |
| P5.3 | Operational memory | Issuer reference facts and provider health are populated from audited inputs and used only for deterministic routing; isolation/admission adversarial tests remain green |
| P5.4 | Real development evaluation | Twenty-four point-in-time cases execute through the configured production reasoner with retrieval, attribution, abstention, latency and measured-AUD-cost results |
| P5.5 | Sealed holdout and confidence review | Twelve issuer/time-isolated blind cases are externally graded; ordinal confidence metadata is reviewed without runtime label access or holdout tuning |
| P5.6 | Final product release | Live smoke, end-to-end canaries, API/UI/export, clean-checkout and release evidence pass; otherwise the product remains explicitly unreleased |

## Driver-lane coverage

The retrieval planner owns a small fixed taxonomy:

1. issuer disclosure and guidance;
2. corporate action, capital raising and block transaction;
3. index inclusion, deletion and rebalance;
4. sector and peer read-through;
5. commodity, FX and macro exposure;
6. analyst or named original research event;
7. genuine no-identifiable-catalyst or incomplete-data outcome.

Each lane has an approved source policy, typed provider outcome, maximum query/document budget and explicit coverage status. The planner may skip a lane only for a persisted, auditable reason.

## Final release gates

- Zero lookahead, incorrect ASX-session attribution, missing material citation, unsupported published claim and provider-failure-to-no-catalyst conversions.
- Primary-source acquisition and timing integrity are reported separately from model attribution.
- Top-1 attribution is at least 75 percent and top-2 at least 90 percent on answerable `EXPLAINED` cases only.
- Required abstention is 100 percent with a non-zero denominator; false abstention is at most 20 percent on answerable cases.
- No materially wrong `HIGH` explanation.
- Equivalent runs reproduce validated decisions, assertion/artifact identities, coverage and policy trace.
- Every evaluated case reports raw counts, denominators, latency, measured AUD cost and source/model/policy/pricing versions.
- Development, sealed holdout and credentialed Live gates must be `PASS`. A missing input is `NOT_RUN`, never a release approval.

## Final deliverables

1. A working Live ASX investigation agent with a bounded, auditable retrieval plan and evidence-linked confidence-rated report.
2. A frozen-corpus evaluation harness, 24-case development results, externally graded 12-case holdout results and per-case failure analysis.
3. A concise decision rationale covering tools/source conflicts, context management, memory boundaries and evaluation/calibration.
4. English workbench, API and Markdown surfaces that expose source coverage, validated decisions, confidence caps and exact controlled passages without chain-of-thought or private provider data.
5. A clean-checkout runbook and final release record that states every external gate truthfully.

## External inputs that remain required

- Runtime-only Gemini, EODHD and discovery-provider credentials.
- Marketstack only if the governed Live fallback is included in the final release gate.
- Twenty-four adjudicated development bundles and a separately controlled twelve-case holdout with an independent grader.
- A reviewed AUD Gemini pricing schedule and provider entitlements sufficient for the selected historical windows.

Credentials, raw provider bodies and holdout labels never enter the repository.
