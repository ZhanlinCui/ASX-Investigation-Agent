# ASX Investigation Agent Master Development Plan

**Last updated:** 21 August 2026
**Product stage:** Phase 4 activation runtime implemented on the recorded-only release candidate; Phase 5 recall and release closure planned; external evaluation and Live release gates OPEN (`NOT_RUN`)

**Recorded architecture record:** `docs/phase-plans/phase-03-causal-investigation-intelligence.md`
**Active delivery plan:** `docs/phase-plans/phase-05-recall-and-release-closure.md`
**Activation record:** `docs/phase-plans/phase-04-live-validation-activation.md`
**Prior phase record:** `docs/phase-plans/phase-02-evidence-complete-live-investigation.md`

## Product contract

The product accepts an ASX-listed equity code and an ASX trading date. It describes the observed move, investigates plausible causes, and returns evidence-linked claims with a confidence band and visible coverage limits.

All monetary values are AUD. User-facing timestamps use the historically correct AEST or AEDT label. Market windows follow the ASX trading calendar. The product does not recommend trades or predict prices.

Four rules govern every release:

1. Code calculates market facts and determines evidence timing.
2. A material claim cannot ship without registered evidence.
3. Provider failure cannot be reported as a genuine empty result.
4. Confidence is an evidence-strength band until a held-out calibration set supports probability language.

## Current state

Phase 1 remains the verified request-to-report vertical slice. Phase 2 now adds durable case versions, replayable checkpoints, governed market providers, secure source snapshots, exact passage retrieval, bounded hypothesis/challenge roles, deterministic validation, confidence caps, external gold-corpus contract validation, provenance display, a 24-case synthetic policy suite and the complete English workbench.

The recorded release candidate passes local backend, frontend and synthetic evaluation gates. It is not a Live-validated release: the 24 real adjudicated point-in-time development cases, 12-case sealed holdout and credentialed Live smoke run remain open. Their absence is reported as `NOT_RUN`, never as a pass.

The controlled agent architecture is substantially implemented: eleven durable investigation stages include ranked hypothesis generation, one gap-directed retrieval opportunity, a separate challenge role and deterministic publication. The largest remaining product gap is Live evidence recall, not another reasoning framework. Initial discovery is still narrow and discovery-only results cannot normally become primary causal evidence. Shared-memory admission is mature but its safe issuer-reference and provider-health paths are not yet operationally populated. The local 24-case evaluation is a synthetic policy sentinel, not proof of real causal accuracy or confidence calibration.

## Phase 2: Evidence-Complete Live Investigation

Phase 2 makes the vertical slice auditable and recoverable for real cases. It keeps one explicit investigation state machine and two bounded model roles. It does not introduce a general multi-agent platform.

### Milestones

| Milestone | Deliverable | Gate |
|---|---|---|
| P2.0 | Contracts and living documentation | Complete |
| P2.1 | Durable case memory | Complete, including compatibility-checked stage checkpoint resume |
| P2.2 | Live market truth | Complete; credentialed smoke not run |
| P2.3 | Evidence and context | Complete |
| P2.4 | Controlled investigation | Complete |
| P2.5 | Confidence semantics | Complete; probability calibration deferred |
| P2.6 | Evaluation | Synthetic sentinels and external 24/12 gold-corpus contract complete; real corpus and sealed holdout open |
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

## Phase 3: Causal Investigation Intelligence

Phase 3 replaces the current coarse hypothesis interface with assertion-bound hypotheses and a deterministic claim compiler. It adds an append-only investigation ledger, explicit shared-memory admission rules, production-path frozen-case evaluation and ordinal calibration metadata for the existing confidence bands.

The proposed sequence is:

1. extract the typed investigation kernel and ledger;
2. add evidence assertions, mechanism tests and claim compilation;
3. enforce run, case and shared-product memory boundaries;
4. execute frozen real cases through the production path;
5. publish calibration counts and release gates;
6. close credentialed Live evidence and workbench gates.

P3.0 through P3.6 are implemented in the recorded release candidate: the domain contract, typed investigation kernel, assertion-bound reasoning, non-causal shared-memory admission, frozen gold execution path, ordinal calibration gates, and audited workbench surfaces are all delivered in code. This is not a Phase 3 release approval. The development gold corpus, sealed holdout and credentialed Live validation gates remain OPEN and `NOT_RUN`. See `evals/results/phase3-evaluation.md` for the fresh release record.

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

Development, regression and sealed holdout cases are separated. Gold labels record the evidence cutoff, leading driver, acceptable alternatives, prohibited future evidence, mechanical flags, coverage expectation and a typed `REQUIRED`, `ALLOWED` or `FORBIDDEN` abstention policy.

Deterministic graders own time, session, citation, numeric and provider-failure checks. Top-1 and top-2 measure only published `EXPLAINED` outcomes; abstentions are evaluated by their separate policy gates. Gold replay compares validated decisions, assertion/artifact identities and policy trace, never private model prose. A model judge may help classify failures but cannot override a hard gate or a human label.

## Phase 4: Live Validation Activation

Phase 4 has implemented its model-usage and measured-AUD-cost readiness boundary and an
EODHD-only credentialed provider-smoke runtime. The smoke validates one completed ASX
session without a model call or causal report. Its credentialed execution, along with a
real 24-case development corpus and separately controlled 12-case holdout, remains open.
Phase 4 exercises the Phase 3 architecture and makes a measured release decision; it does
not expand product scope. See `docs/phase-plans/phase-04-live-validation-activation.md`.

## Phase 5: Recall and Release Closure

Phase 5 is the final pre-release delivery phase. It adds a deterministic, inspectable retrieval plan across a small fixed set of driver lanes, governed acquisition of approved primary documents, and operational use of non-causal issuer reference/provider-health memory for routing only. It then executes the existing production-path evaluation against 24 real development cases and a separately controlled 12-case sealed holdout before making a release decision.

The phase deliberately keeps the current safety boundaries: one typed kernel, two structured Gemini calls, one adaptive retrieval round, no model-controlled providers, no cross-case conclusions and ordinal confidence only. Search remains discovery; exact frozen approved sources remain the causal evidence boundary.

P5.0 through P5.3 implementation is delivered on the Phase 5 branch: durable bounded retrieval plans, governed primary-source promotion, retrieval-failure abstention and operational non-causal memory routing are covered by local regression tests. P5.4 through P5.6 remain open because real point-in-time corpora, independent holdout grading and credentialed Live execution are not yet present. The authoritative scope, milestones, gates and final deliverables are in `docs/phase-plans/phase-05-recall-and-release-closure.md`; executable tasks are in `docs/superpowers/plans/2026-08-21-final-delivery-closure.md`.

## Later phases

A post-release phase may add probability calibration only after a materially larger independently labelled corpus supports that language. PostgreSQL/object storage deployment, authentication, multi-user access and broader operational observability also remain later work.

Evidence graphs, collaboration, alerts, mobile authoring, trade execution and automatic cross-case learning remain deferred until the final Phase 5 release gates pass.

## Change control

The master plan records product sequence and gates. The active phase plan records implementation tasks. Product interaction rules live in `design requirement document v1.md`. The long R&D specification remains reference material and does not override current code or this plan.

Any change to source precedence, time eligibility, confidence semantics, memory isolation or holdout policy requires an explicit decision record and new regression tests.
