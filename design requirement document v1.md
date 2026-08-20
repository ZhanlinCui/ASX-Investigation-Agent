# ASX Investigation Workbench
## Product Design Requirement

**Version:** 2.4
**Status:** Phase 2.8 product baseline; P3.0–P3.5 complete; P3.6 workbench and release evidence in progress
**Language:** English interface  
**Primary user:** Analyst or investigator reviewing an unusual ASX equity move

## Product purpose

The workbench must let a user answer six questions without trusting an unsupported narrative:

1. What moved during the selected ASX session?
2. Which explanation leads, and which alternatives remain?
3. Which evidence supports or contradicts each claim?
4. Was each source available before the relevant move?
5. Which data sources or documents were missing or in conflict?
6. Why does the result have its confidence band?

The workbench is an investigation product. It is not a trading terminal, a portfolio tool or an open-ended chatbot.

## Product state

### Implemented baseline

- Ticker and ASX date case creation.
- Recorded and basic live modes.
- Market-move summary in AUD.
- Leading assessment, confidence label and evidence list.
- JSON and Markdown results.
- Durable lifecycle and recoverable-failure states.

### Implemented in Phase 2

- Persistent case archive and restart-safe running state.
- Ranked hypotheses and one challenge result.
- Exact evidence passages with source timing and authority.
- Coverage gaps and material source conflicts.
- Confidence drivers, caps and investigation completeness as separate fields.
- Trace events and provider-stage progress.
- Child case versions for typed refinements.
- Safe PDF, text and URL source ingestion.

### Deferred

- Authentication, teams, comments and sharing.
- Alerts, continuous monitoring and scheduled investigations.
- Trade ideas, recommendations, forecasts and execution.
- General plugin marketplace.
- Automatic cross-case learning.
- Complex evidence-graph authoring.
- Mobile authoring.

### Delivered in Phase 3

- Assertion-level evidence references between passages and hypotheses.
- Visible causal mechanism tests and rejected-hypothesis reasons.
- An append-only investigation ledger with policy and artifact lineage.
- Shared issuer reference facts admitted as bounded, point-in-time `CONTEXT_ONLY` context. They cannot support a hypothesis or claim, and prior case conclusions and holdout labels are rejected.
- Frozen, hash-verified gold bundles that run through the production investigation path. Blind holdout reports never load or display sealed labels.
- Reviewed ordinal calibration metadata and release gates. Confidence remains a band, not a probability; missing external gold evaluation remains visibly `NOT_RUN`.

### Proposed for later Phase 3 milestones

- Calibration sample status for LOW, MEDIUM and HIGH bands.
- Blind evaluation export without development or sealed labels.

These items are planned behavior. They are not part of the current recorded release until their milestone gates pass.

## Design direction

Keep the supplied warm research-desk language: parchment canvas, soft-paper cards, hairline borders, graphite metadata, ink text and one deep-teal active colour. Do not add gradients, glass effects, decorative imagery or dashboard ornament.

The interface may become denser as evidence is added, but it should remain calm. Evidence and uncertainty receive more visual weight than model prose.

### Tokens

| Role | Value |
|---|---:|
| Canvas | `#FAF8F5` |
| Surface | `#FDFBFA` |
| Border | `#D1D1CD` |
| Ink | `#27251E` |
| Graphite | `#72706B` |
| Teal | `#016A71` |
| Positive | `#1F6B4F` |
| Negative | `#9C392A` |
| Warning | `#9B651C` |
| Conflict | `#A34130` |

Use Inter or a system sans-serif at 400 and 500 weight. Prices, dates, percentages and statistics use tabular numerals. Use borders before shadows.

## Information architecture

The desktop shell retains a quiet left rail and one main case workspace.

```text
Investigate
Case archive
  -> Case overview
  -> Hypotheses
  -> Evidence and source passage
  -> Confidence and coverage
  -> Report and trace
Method
```

The case header displays instrument, ASX date, AEST/AEDT label, lifecycle, investigation outcome, mode and version. Lifecycle and outcome are never collapsed into one label.

## Primary flows

### Start an investigation

The user enters a ticker, ASX date and mode. Optional source IDs can attach uploaded or fetched documents. The client submits typed fields; natural-language parsing is not required for Phase 2.

The running view lists persisted stages. Completed stages remain visible after refresh. A failed recoverable stage names the safe retry action without exposing provider secrets.

### Review a completed case

The overview presents observed market facts first, followed by the leading assessment. Ranked hypotheses show leading, alternative, mechanical, rejected or insufficient-evidence status.

Each hypothesis opens its supporting evidence, contradicting evidence and validation results. Residual returns and anomaly scores are labelled as measurements, not causes.

### Inspect evidence

Evidence rows display source, title, publication time, retrieval time, authority, temporal role, claim links and locator. Selecting a row opens the exact frozen passage. Post-move evidence is visibly labelled context.

Coverage gaps and source conflicts appear next to the affected claim. They cannot be hidden in trace-only views.

### Inspect confidence

Confidence displays a LOW, MEDIUM or HIGH band. The drawer lists positive factors, deductions, deterministic caps, unresolved alternatives and investigation completeness.

The interface does not render the internal feature score as an empirical probability. `UNCALIBRATED` remains visible until a future release has sufficient held-out calibration evidence.

### Refine a case

A user may change the evidence cutoff, choose primary-only sources, exclude evidence or attach a source. The server creates a child version. The original report remains available and a comparison lists changed evidence, claims, gaps and confidence caps.

## Required states

| State | Treatment |
|---|---|
| Queued or running | Show persisted completed stages and the active stage |
| Explained | Show the leading claim and alternatives with evidence |
| No identifiable catalyst | State that the search completed without an eligible catalyst |
| Insufficient evidence | State which evidence or coverage is missing |
| Incomplete data | State which required provider or historical source is unavailable |
| Material conflict | Show both source values and the selected field policy |
| Failed recoverable | Name the failed stage and provide retry |
| Failed | Preserve the trace and explain why retry is unsafe |

Provider failure is never rendered as “no news” or “no catalyst.”

## Component responsibilities

| Component | Responsibility |
|---|---|
| `InvestigationInput` | Typed ticker, date, mode and attached source creation |
| `CaseArchive` | Persisted cases, versions, status and last update |
| `CaseHeader` | Identity, date, timezone, lifecycle, outcome and version |
| `StageTimeline` | Replayable progress and failure stage |
| `MarketMoveCard` | Deterministic move and data resolution |
| `HypothesisList` | Ranked explanations, alternatives and rejection reason |
| `EvidenceList` | Source metadata, role, timing and claim links |
| `SourceViewer` | Exact frozen passage and locator |
| `CoveragePanel` | Missing providers, documents and affected claims |
| `ConflictPanel` | Conflicting values and field-resolution policy |
| `ConfidencePanel` | Band, caps, factors, alternatives and completeness |
| `CaseVersionCompare` | Parent-child changes |
| `ReportView` | Markdown generated from validated state |
| `TraceView` | Public stage, provider and validation events |

## Data and safety rules

- Every visible material fact maps to an API field, evidence ID or quantitative result ID.
- Evidence links open frozen content rather than a newly fetched page where possible.
- The UI does not calculate returns, choose sources or adjust confidence.
- Documents are untrusted data. Their embedded instructions are never shown as system instructions.
- Secrets, raw credentials, hidden prompts and chain-of-thought are never displayed.
- User source fetching rejects private and reserved network targets.
- All status meanings are expressed with text and icons, not colour alone.

## Accessibility and responsive behaviour

Meet WCAG 2.1 AA for the desktop flow. Controls need visible focus, labels and keyboard operation. Evidence passages must be selectable and readable without a pointer. Charts need text summaries.

At 1024 to 1279 px, secondary panels stack below the overview. Below 1024 px, use a tabbed read-only case view; dense authoring remains desktop-first.

## Phase 2 acceptance criteria

- Refreshing a running or completed case preserves its state.
- A user can distinguish lifecycle, outcome, confidence and completeness.
- Every material claim opens its registered supporting passage.
- Post-move evidence cannot appear as causal support.
- Missing providers and source conflicts are visible beside affected conclusions.
- Retry resumes only a recoverable case stage.
- Refinement creates a child version and does not mutate the parent.
- JSON, Markdown and UI present the same claims, evidence and caps.
- The UI introduces no market fact absent from backend state.
- The production build and automated accessibility checks pass.

## Product principle

Make the answer easy to challenge. The product earns trust by preserving provenance, timing, alternatives and limits.
