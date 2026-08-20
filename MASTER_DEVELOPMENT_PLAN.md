# ASX Investigation Agent Master Development Plan

**Last updated:** 20 August 2026  
**Product stage:** Phase 2 recorded release candidate

**Authoritative phase plan:** `docs/phase-plans/phase-02-evidence-complete-live-investigation.md`

## Product contract

The product accepts an ASX-listed equity code and an ASX trading date. It describes the observed move, investigates plausible causes, and returns evidence-linked claims with a confidence band and visible coverage limits.

All monetary values are AUD. User-facing timestamps use the historically correct AEST or AEDT label. Market windows follow the ASX trading calendar. The product does not recommend trades or predict prices.

Four rules govern every release:

1. Code calculates market facts and determines evidence timing.
2. A material claim cannot ship without registered evidence.
3. Provider failure cannot be reported as a genuine empty result.
4. Confidence is an evidence-strength band until a held-out calibration set supports probability language.

## Current state

Phase 1 remains the verified request-to-report vertical slice. Phase 2 now adds durable case versions, replayable stages, governed market providers, secure source snapshots, exact passage retrieval, bounded hypothesis/challenge roles, deterministic validation, confidence caps, a 24-case synthetic policy suite and the complete English workbench.

The recorded release candidate passes local backend, frontend and synthetic evaluation gates. It is not a Live-validated release: the 24 real adjudicated point-in-time development cases, 12-case sealed holdout and credentialed Live smoke run remain open. Their absence is reported as `NOT_RUN`, never as a pass.

## Phase 2: Evidence-Complete Live Investigation

Phase 2 makes the vertical slice auditable and recoverable for real cases. It keeps one explicit investigation state machine and two bounded model roles. It does not introduce a general multi-agent platform.

### Milestones

| Milestone | Deliverable | Gate |
|---|---|---|
| P2.0 | Contracts and living documentation | Complete |
| P2.1 | Durable case memory | Complete for case/version/event durability; exact stage-output resume remains open |
| P2.2 | Live market truth | Complete; credentialed smoke not run |
| P2.3 | Evidence and context | Complete |
| P2.4 | Controlled investigation | Complete |
| P2.5 | Confidence semantics | Complete; probability calibration deferred |
| P2.6 | Evaluation | Harness and 24 synthetic sentinels complete; real corpus and sealed holdout open |
| P2.7 | Workbench release | Workbench, CI and clean-checkout gate complete; credentialed Live smoke open |

Each milestone uses test-first implementation and an independent review checkpoint. A later milestone may not hide a failed earlier gate.

### Phase 2 release gates

- Lookahead violations: 0.
- Incorrect ASX session attribution: 0.
- Missing citations on material claims: 0.
- Material unsupported claims: 0.
- Provider failures misreported as no catalyst: 0.
- Recorded-case reproducibility: 100% after volatile IDs and retrieval timestamps are normalized.
- Every confidence cap has a direct unit test.
- Holdout results include raw counts and per-case failure analysis.
- A clean checkout runs recorded mode, the API, the UI build and the evaluation smoke suite.
- Live completion requires externally supplied provider credentials. Without them, the release report states that the live gate was not run.

## Architecture boundaries

| Boundary | Owns | Must not own |
|---|---|---|
| Domain | Schemas, enums and invariants | Network, database or model calls |
| Market | ASX sessions, returns, anomaly and mechanical checks | Causal narrative |
| Providers | Typed acquisition outcomes and source provenance | Silent fallback or causal interpretation |
| Evidence | Snapshots, passages, timing, deduplication, retrieval and conflicts | Final confidence |
| Investigation | Bounded state transitions and model roles | Market calculations |
| Confidence | Observable features, caps, bands and abstention | Model-supplied percentages |
| Storage | Cases, versions, events, artifacts and cache | Cross-case conclusions |
| Report/API/UI | Presentation of validated state | New financial facts |
| Evaluation | Frozen fixtures, graders and release evidence | Production memory mutation |

## Memory policy

Case state is isolated. A completed case version is immutable. Refinements create a child version and retain the parent.

The only cross-case state allowed in production is versioned policy, ASX calendar data, provider health, TTL cache entries, confidence-rule versions and calibration artifacts. Prior claims, prior model summaries and holdout labels never enter a new case context.

Provider cache is not memory. It has a source, retrieval time, expiry and content hash.

## Data policy

- EODHD is the primary ASX daily-price source.
- Marketstack is the price fallback.
- Source values are never averaged.
- Material price or volume disagreements remain visible and cap confidence.
- Tavily and GDELT are discovery sources, not independent causal proof.
- Issuer IR material and explicitly supplied documents are preferred causal sources.
- ASX pages are not scraped.
- The default live investigation window is the trailing 12 months.

## Evaluation policy

Development, regression and sealed holdout cases are separated. Gold labels record the evidence cutoff, leading driver, acceptable alternatives, prohibited future evidence, mechanical flags, coverage expectation and whether abstention is acceptable.

Deterministic graders own time, session, citation, numeric and provider-failure checks. A model judge may help classify failures but cannot override a hard gate or a human label.

## Later phases

Phase 3 may add probability calibration after a large enough independently labelled corpus exists. It may also add PostgreSQL/object storage deployment, authentication, multi-user access and stronger observability.

Evidence graphs, collaboration, alerts, mobile authoring, trade execution and automatic cross-case learning remain deferred until the Phase 2 release gates pass.

## Change control

The master plan records product sequence and gates. The active phase plan records implementation tasks. Product interaction rules live in `design requirement document v1.md`. The long R&D specification remains reference material and does not override current code or this plan.

Any change to source precedence, time eligibility, confidence semantics, memory isolation or holdout policy requires an explicit decision record and new regression tests.
