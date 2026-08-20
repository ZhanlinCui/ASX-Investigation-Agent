# ASX Investigation Workbench
## Frontend Design Specification

**Version:** 2.0  
**Status:** M8 design baseline  
**Scope:** Desktop-first evidence workbench for a completed or running ASX investigation.

## 1. Purpose

The workbench helps an analyst answer five questions from one case view:

1. What moved?
2. What is the leading explanation?
3. What evidence supports it?
4. What alternatives or conflicts remain?
5. Why is confidence high, low, or capped?

The UI is an inspection surface, not a trading dashboard or generic chatbot. It renders API-backed facts, evidence, validation, and uncertainty. It must never create financial facts from chat text or client-side inference.

## 2. Release scope

M8 includes:

- Start a new investigation with a natural-language prompt or ticker and ASX date.
- Case header, market move summary, price chart, primary assessment, and competing hypotheses.
- Event timeline with point-in-time eligibility.
- Evidence list, exact-passage source viewer, quantitative validation, and confidence explanation.
- Markdown report, basic trace, explicit incomplete-data and conflict states.
- Typed conversational refinements that create a new case version.

Deferred: evidence graph, command palette, advanced counterfactuals, collaboration, mobile authoring, and full evaluation administration.

## 3. Design direction

Use the calm research-desk character of the supplied Perplexity reference: warm paper surfaces, compact controls, restrained elevation, a single brand accent, and a search-led entry point. Adapt it for an analytical workbench with denser data and explicit risk states.

Avoid gradients, glass effects, decorative imagery, oversized chat bubbles, and dashboard ornament. The evidence should carry the visual weight.

### Tokens

| Role | Value | Use |
|---|---:|---|
| Canvas | `#FAF8F5` | App background |
| Surface | `#FDFBFA` | Cards, drawers, source passages |
| Border | `#D1D1CD` | Hairline separation |
| Ink | `#27251E` | Primary text and primary action |
| Graphite | `#72706B` | Metadata and inactive controls |
| Teal | `#016A71` | Selected navigation, links, focus, active filters |
| Positive | `#1F6B4F` | Positive movement, paired with label/icon |
| Negative | `#9C392A` | Negative movement, paired with label/icon |
| Warning | `#9B651C` | Partial data and preliminary state |
| Conflict | `#A34130` | Material disagreement or failed validation |

Use Inter or a system sans-serif at 400 and 500 weight. Use tabular numerals for all prices, dates, percentages, and statistics. Default UI text is 14px; metadata is 12px; headline metrics are 28px. Cards use a 16px radius, inputs 12px, buttons 6px, and chips a full radius. Use borders to separate surfaces; card shadow is limited to `0 1px 2px rgb(0 0 0 / 8%)`.

## 4. Application structure

The desktop shell has a 232px left rail and one fluid workspace. The landing page uses a centered 720px investigation input. A case uses a 12-column grid at 1280px or wider; the content width may expand beyond the landing-page measure because evidence and charts require room.

```text
+----------------------+--------------------------------------------------+
| ASX Investigator     | BHP Group Limited - 19 Feb 2026 - AEDT          |
|                      | Completed · High confidence                      |
| Investigate          +--------------------------------------------------+
| Cases                | Market move        Primary assessment            |
|                      | Timeline           Hypotheses                    |
|                      | Evidence           Quantitative validation        |
|                      | Report             Trace                          |
+----------------------+--------------------------------------------------+
```

The left rail is quiet: ink brand mark, navigation, and case identity. The active item has a teal fill and white label. The header stays visible within a case and shows instrument, date, timezone, lifecycle state, confidence, and current case version.

## 5. Key screens and interactions

### New investigation

The main element is a large warm-paper input: "Investigate BHP on 19 February 2026". It accepts natural language but shows ticker and date fields as an accessible alternative. Below it, display a small set of recent cases. Submitting creates a new case and moves to its running state.

### Case overview

Place the market move and primary assessment first. The move card shows close return, abnormal return when available, volume signal, turnover, market-data coverage, and a compact price chart. The assessment states the leading hypothesis, claim status, and confidence without implying that confidence is causal proof.

Below, show a chronological timeline and a ranked hypothesis list. Each hypothesis is labelled as leading, alternative, mechanical, rejected, or insufficient evidence. A hypothesis opens its supporting evidence, contradicting evidence, and validation results.

### Evidence and source viewer

Evidence rows show source, timestamp, authority, eligibility, claim links, and a concise extracted passage. Selecting a row opens a right-side viewer at the exact registered passage. Pre-move and post-move evidence are visibly different; post-move material is context unless the backend marks it causally eligible.

### Quantitative validation and confidence

Quantitative validation lists the method, result, availability, and limits. It labels residual returns as model-unexplained, never as a cause.

Selecting confidence opens a drawer with supporting factors, deductions, deterministic caps, evidence coverage, unresolved conflicts, calibration version, and alternatives. Confidence, completeness, and claim support are displayed as separate values.

### Refinements

The case input supports bounded requests such as restricting sources, changing the time cutoff, adding peers, or excluding evidence. The client sends a typed mutation; it never recalculates the case locally. A successful mutation creates a new case version, preserves the parent version, and shows what changed in the trace.

## 6. State and data rules

The frontend consumes the canonical investigation response and schema-derived client types. Chat is only a presentation and control surface for the same structured case state.

| State | Required treatment |
|---|---|
| Running | Show completed sections immediately; mark later sections as pending. |
| Preliminary | Show the result with a clear preliminary label. |
| Partial | Show missing providers, unavailable controls, and coverage impact. |
| Conflicted | Keep conflicting values and source authority visible. |
| Insufficient evidence | State the abstention; do not provide a substitute narrative. |
| Failed | State the failing stage and a safe retry action. |

All material visible facts require an API field, evidence ID, or quantitative-result ID. Citations open their registered locator. The UI does not expose chain-of-thought, hidden prompts, or raw secret-bearing provider payloads.

## 7. Component set

| Component | Responsibility |
|---|---|
| `CaseHeader` | Case identity, lifecycle, version, confidence entry point |
| `InvestigationInput` | Natural-language and structured case creation |
| `MarketMoveCard` | Deterministic movement summary and coverage |
| `PriceChart` | Price series with accessible text summary and event markers |
| `AssessmentCard` | Leading claim, support status, and linked evidence |
| `Timeline` | Event order and temporal eligibility |
| `HypothesisList` | Ranked explanations, alternatives, and rejection reasons |
| `EvidenceList` / `SourceViewer` | Evidence rows and exact source passage |
| `QuantValidation` | Tests, results, data availability, and limits |
| `ConfidenceDrawer` | Drivers, caps, gaps, conflicts, and calibration metadata |
| `CaseMutation` | Typed refinement and versioned rerun |
| `ReportView` / `TraceView` | Markdown report and auditable execution summary |

## 8. Accessibility and responsive behaviour

Meet WCAG 2.1 AA for the supported desktop workflow. Every status has text and an icon in addition to colour. Provide visible focus, keyboard navigation, semantic headings, labelled controls, chart summaries, and source-passages that can be selected and read without a pointer.

At 1024–1279px, retain the left rail and stack secondary panels below the overview. Below 1024px, provide a simplified read-only or tabbed case view; authoring and dense side-by-side analysis are not part of M8.

## 9. Acceptance criteria

- A user can start an ASX investigation and understand the market move without reading the chat transcript.
- Each material claim links to evidence or a quantitative result, and each evidence link opens the exact registered passage.
- The case makes leading, alternative, mechanical, post-event, conflicted, incomplete, and abstained states unambiguous.
- A user can inspect why confidence has its value and distinguish it from investigation completeness.
- A source or time-cutoff refinement creates a visible, versioned rerun rather than silently altering the original case.
- The frontend only renders facts present in structured backend state.

## 10. Design principle

Make the answer easy to challenge. The interface earns trust through provenance, timing, and visible limits rather than visual certainty.
