# Product Design

**Version:** 3.0 release candidate<br>
**Language:** English<br>
**Status:** Product packaging delivered locally; external development, holdout and Live gates `NOT_RUN`

## Design intent

The workbench helps an analyst answer six questions without trusting unsupported model prose:

1. What moved during the selected ASX session?
2. Which explanation leads, and what alternatives remain?
3. What exact evidence supports or contradicts each claim?
4. Was that evidence available before the relevant move?
5. Which sources are missing, failed or in conflict?
6. Which facts, caps and coverage conditions produced the confidence band?

This is an investigation product, not a trading terminal or open-ended chatbot. The interface should feel like a calm research desk: information-dense enough for an audit, restrained enough that uncertainty is easy to see.

## Visual system

The release uses one light theme with a parchment canvas, soft-paper surfaces, graphite metadata, deep ink text and a single teal action colour. Borders establish hierarchy before shadows. The product uses no gradients, glass effects, decorative illustrations, complex charts or dashboard ornament.

| Token | Value | Use |
| --- | --- | --- |
| Canvas | `#f6f3ee` | Application background |
| Surface | `#fffdf9` | Cards and evidence sheets |
| Border | `#d5d0c8` | Quiet structure |
| Ink | `#24231f` | Primary text |
| Graphite | `#696762` | Metadata |
| Teal | `#08777a` | Active navigation and actions |
| Positive | `#2b7357` | Supported or complete |
| Warning | `#a36516` | Partial or skipped |
| Negative | `#a04132` | Failure or material conflict |

Type uses a system sans-serif. Prices, dates, returns and hashes use tabular numerals. Motion is limited to short state transitions and focus movement; evidence never animates decoratively.

## Information architecture

The desktop shell has a persistent archive rail and one case workspace. Completed reports use three reading levels:

### Overview

- deterministic market-move facts;
- validated leading assessment;
- confidence, completeness and caps;
- seven-lane investigation plan;
- coverage gaps and material conflicts.

### Evidence

- ranked hypotheses and challenge disposition;
- frozen evidence register;
- exact version-scoped passage drawer;
- typed assertions and deterministic mechanism tests;
- supporting and contradicting evidence IDs.

### Audit

- parent-child version comparison;
- public decision-ledger stages and hashes;
- calibration and release-gate state;
- Markdown export;
- safe trace metadata.

The interface never exposes search queries, provider bodies, memory values, prompts, private model prose or chain-of-thought.

## Core flows

### Start and follow a case

The user enters an ASX code, trading date and `LIVE` or `RECORDED` mode. PDF or text sources can be attached with a declared Sydney publication time. Running cases show replayable stage progress. A recoverable failure names the failed boundary and offers retry without leaking provider details.

### Review a result

The report separates lifecycle from outcome. `COMPLETED` is not the same as `EXPLAINED`; a completed case may legitimately report `NO_IDENTIFIABLE_CATALYST`, `INSUFFICIENT_EVIDENCE` or `INCOMPLETE_DATA`. Confidence and completeness appear as separate concepts. `LOW`, `MEDIUM` and `HIGH` are ordinal evidence-strength bands, never probabilities.

### Inspect evidence

Each evidence row exposes safe authority, timing, hash and locator metadata. Exact text is fetched only from `GET /api/v1/evidence/{evidence_id}/content?version_id={version_id}`. The drawer traps attention within the evidence task, focuses its close control on open and closes with Escape. Retrospective material remains context and cannot appear as same-session causal support.

### Refine and compare

Primary-only, evidence exclusion, source attachment and evidence cutoff refinements create immutable child versions. The Audit view compares parent and child public reports; the original remains available through its case-scoped version endpoint.

## Required states

| State | Required treatment |
| --- | --- |
| Loading or queued | Name the current durable stage and completed checkpoints |
| Explained | Show the selected claim, alternatives and direct evidence links |
| Required abstention | Lead with the missing support and confidence cap |
| No identifiable catalyst | State that required retrieval completed without an eligible cause |
| Incomplete data | Name the failed required provider or unavailable time window |
| Material conflict | Present both source values and the deterministic resolution policy |
| Recoverable failure | Preserve trace and offer a scoped retry |
| Legacy report | Render safely when newer optional fields such as `retrieval_plan` are absent |

Provider failure must never be rendered as “no news” or “no catalyst.”

## Accessibility and responsive behavior

- Every control has a visible focus state and text label.
- Overview, Evidence and Audit use `tablist`, `tab`, `tabpanel`, arrow-key selection and correct `tabIndex`.
- The evidence drawer uses dialog semantics, an accessible name, initial focus and Escape close.
- Status never relies on colour alone.
- At 1440px the archive and case sheet remain visible together.
- At 1024px secondary groups stack without hiding audit fields.
- At 768px the sidebar becomes a compact header and report navigation remains reachable.
- At 390px the review flow is a single readable column with no horizontal overflow; authoring remains intentionally compact.

## Product boundaries

The release candidate does not include authentication, teams, alerts, portfolios, forecasts, trade recommendations, execution, plugin marketplaces, a vector database, automatic cross-case learning or mobile authoring. These are not missing dashboard features; they are deliberate scope boundaries.

## Acceptance rule

The UI may only present facts and decisions that exist in the public API projection. JSON, Markdown and the workbench must agree on claims, evidence IDs, retrieval-lane coverage and confidence caps. A polished surface cannot change an external evaluation or Live gate from `NOT_RUN` to `PASS`.
