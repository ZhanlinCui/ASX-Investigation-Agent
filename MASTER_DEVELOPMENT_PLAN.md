# ASX Unusual Trading Investigation Agent Master Development Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement each phase plan task by task. Every phase must have its own reviewed execution plan before code changes begin.

**Goal:** Build a working agent that accepts an ASX-listed equity ticker and an ASX date, explains the unusual price move, rates the confidence of each material claim, and cites the evidence behind each claim.

**Architecture:** The system is a small investigation pipeline with deterministic market and time logic, a normalized evidence registry, one investigator model call, one critic model call, an explicit claim-evidence graph, and an empirically tested confidence layer. The human-readable report and any user interface render the same structured investigation state.

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, LangGraph, httpx, pandas, NumPy, SciPy, statsmodels, scikit-learn, DuckDB, SQLite, PyArrow/Parquet, PyMuPDF, pytest, OpenTelemetry.

## Global Constraints

- Inputs are an ASX ticker and an investigation date. Optional constraints may narrow sources, peers, or the point-in-time cutoff.
- The supported launch universe is ASX-listed ordinary equities. Other security types must return an explicit unsupported-instrument result until added through a later decision record.
- All user-facing monetary figures are in AUD. Converted figures retain the original amount, currency, FX rate, FX timestamp, and FX source.
- All user-facing timestamps use the historically correct AEST or AEDT label. Internal timestamps are timezone-aware and use `Australia/Sydney` for local rendering.
- The ASX trading calendar and date-specific session rules are authoritative. The system never silently changes a non-trading date.
- Facts that code can calculate or verify do not come from an LLM. This includes prices, returns, volumes, timestamps, calendar rules, currency conversion, corporate actions, statistical results, and citation existence.
- Evidence published after the relevant price movement cannot establish the cause of that movement. It may be retained as retrospective context with an explicit role.
- Every material factual or causal claim links to registered evidence or a registered quantitative result.
- Provider failure is different from an empty successful result. Incomplete source coverage remains visible and can force abstention.
- Conflicting values remain visible. Resolution follows field-specific source policy and never silently averages disagreement.
- Confidence is computed from observable features, capped by known limitations, and calibrated against held-out cases. The LLM does not assign the final probability.
- The agent may return `NO_IDENTIFIABLE_CATALYST`, `INSUFFICIENT_EVIDENCE`, or `INCOMPLETE_DATA`.
- The system does not provide trading recommendations, portfolio advice, price predictions, or trade execution.
- `third_party/ai-hedge-fund` is reference material. Any migrated code must be reviewed, adapted to ASX semantics, covered by local tests, and carry the required MIT attribution.

---

## 1. Plan Authority and Maintenance

This file is the project-level source of truth for sequence, scope, and milestone status. It is derived from:

- `ASX Unusual Trading Investigation Agent.md`
- `design requirement document v1.md`

The two design documents explain the intended system and product. This plan decides implementation order and deliberately postpones features that do not help the core assignment pass unseen cases.

Update this file when a milestone changes state, a gate changes, or a phase is split. Record material architecture or data-policy changes in `docs/decisions/` and link them from the relevant phase. Do not rewrite completed milestone evidence; append the new result and preserve the earlier record.

Status values:

- `[ ]` Not started
- `[-]` In progress
- `[x]` Complete and accepted
- `[!]` Blocked, with the blocking condition recorded under the milestone

## 2. Product Definition

### 2.1 Required launch outcome

A successful run produces:

1. A resolved ASX instrument and historical trading session.
2. A deterministic description of the move and why it qualifies as unusual.
3. A ranked set of materially different causal hypotheses.
4. Supporting and contradicting evidence for each surviving hypothesis.
5. Temporal and quantitative validation results.
6. Claim-level confidence, primary-hypothesis confidence, and investigation completeness as separate values.
7. A structured JSON result and a readable Markdown report.
8. A reproducible trace showing tools, inputs, outputs, source versions, model versions, and validation decisions.

### 2.2 Core scope

The first release includes:

- ASX instrument and trading-session resolution.
- Daily and available intraday market forensics.
- Corporate-action and mechanical-move checks.
- ASX disclosure retrieval and document extraction.
- A bounded set of external market, sector, peer, commodity, FX, and news sources.
- Evidence normalization, deduplication, conflict handling, and exact citation locators.
- Hypothesis generation, deterministic validation, contradiction search, and claim construction.
- Confidence rules, calibration, and abstention.
- Recorded and live execution modes.
- A CLI or API entry point, JSON output, Markdown report, trace, and evaluation report.

### 2.3 Deferred scope

The following work does not block the working-agent deliverable:

- Order-book analysis.
- Portfolio or trade features.
- Evidence graph visualization.
- Advanced causal counterfactual simulation.
- Multi-user collaboration, comments, and sharing.
- Alerts and continuous monitoring.
- Mobile authoring.
- Cross-case narrative memory.
- A broad multi-agent organization or role-playing debate system.

## 3. Architecture Baseline

```text
InvestigationRequest
        |
        v
Instrument and Session Resolver
        |
        v
Deterministic Market Forensics
        |
        +---------------------------+
        |                           |
        v                           v
Primary Evidence Retrieval     Market Context Retrieval
        |                           |
        +-------------+-------------+
                      v
               Evidence Registry
                      |
                      v
             Investigator LLM Node
                      |
                      v
      Temporal, Market, and Conflict Validation
                      |
                      v
                 Critic LLM Node
                      |
                      v
              Claim-Evidence Graph
                      |
                      v
        Confidence Rules and Calibrator
                      |
                      v
                Citation Validator
                      |
          +-----------+-----------+
          v                       v
       JSON API              Markdown Report
```

### 3.1 Component boundaries

| Component | Responsibility | Must not do |
|---|---|---|
| Domain | Canonical request, instrument, session, evidence, hypothesis, claim, conflict, confidence, and report models | Network calls or model calls |
| Providers | Typed access to external market, disclosure, corporate-action, FX, commodity, and news sources | Interpret causality |
| Market | Session logic, returns, anomalies, factor controls, event studies, and mechanical-event checks | Read unregistered prose evidence |
| Evidence | Fetch, snapshot, parse, retrieve, rank, deduplicate, register, and resolve source conflicts | Assign final causal confidence |
| Investigation | Orchestrate hypotheses, validation, critic review, claims, and bounded retrieval loops | Calculate market facts in prompts |
| Confidence | Compute features, apply caps, calibrate, and decide abstention | Accept an LLM confidence percentage |
| Report | Validate citations and render structured state | Introduce new facts |
| Evaluation | Run fixed cases, grade intermediate and final outputs, and publish metrics | Mutate production case memory |

### 3.2 Target repository structure

```text
ASX Investigation Agent/
|-- src/asx_investigator/
|   |-- domain/
|   |-- providers/
|   |-- market/
|   |-- evidence/
|   |-- investigation/
|   |-- confidence/
|   |-- report/
|   |-- api/
|   `-- storage/
|-- tests/
|   |-- unit/
|   |-- integration/
|   `-- regression/
|-- evals/
|   |-- cases/
|   |-- fixtures/
|   |-- gold/
|   |-- graders/
|   `-- reports/
|-- docs/
|   |-- decisions/
|   |-- source-policy/
|   `-- phase-plans/
|-- third_party/
|   `-- ai-hedge-fund/
|-- pyproject.toml
|-- README.md
`-- MASTER_DEVELOPMENT_PLAN.md
```

LangGraph enters only after the deterministic services and evidence registry have stable interfaces. It owns orchestration and checkpointing, not domain logic. The launch graph contains two LLM nodes: Investigator and Critic.

## 4. Milestone Map

| Milestone | Result | Depends on | Status |
|---|---|---|---|
| M0 | Scope, contracts, source policy, and eval protocol frozen | None | [ ] |
| M1 | ASX domain truth layer passes reference tests | M0 | [ ] |
| M2 | Market forensics produces verified anomaly results | M1 | [ ] |
| M3 | Evidence can be retrieved, frozen, cited, and audited | M0, M1 | [ ] |
| M4 | End-to-end investigation graph produces supported claims | M2, M3 | [ ] |
| M5 | Confidence and abstention are measurable and calibrated | M4 | [ ] |
| M6 | Blind evaluation results meet release gates | M5 | [ ] |
| M7 | Working agent is packaged and reproducible | M6 | [ ] |
| M8 | Minimal investigation workbench exposes the proof layer | M7 | [ ] |
| M9 | Release candidate passes security, reliability, and documentation review | M8 | [ ] |

M7 satisfies the original working-agent delivery. M8 and M9 turn the core into the designed workbench without holding the core evaluation hostage to frontend scope.

## 5. Phase 0: Contracts, Source Policy, and Project Foundation

**Milestone:** M0

**Purpose:** Remove ambiguity before implementation. Fix the meaning of time, evidence, confidence, source disagreement, and success.

### Deliverables

- `pyproject.toml` with runtime, development, lint, type-check, and test dependencies.
- `src/asx_investigator/domain/` with the canonical v1 schemas.
- `docs/decisions/ADR-0001-architecture-boundaries.md`.
- `docs/decisions/ADR-0002-source-of-record-policy.md`.
- `docs/decisions/ADR-0003-confidence-semantics.md`.
- `docs/decisions/ADR-0004-evaluation-label-protocol.md`.
- `docs/source-policy/provider-matrix.md`.
- `evals/cases/sentinel-manifest.yaml` defining the initial deterministic edge cases.
- `docs/phase-plans/phase-01-domain-truth.md` as the first task-level TDD execution plan.

### Work packages

- [ ] Define the supported security universe and explicit rejection results.
- [ ] Freeze `InvestigationRequest`, `InstrumentIdentity`, `TradingSession`, `MarketMove`, `EvidenceItem`, `Hypothesis`, `ValidationResult`, `Claim`, `ConfidenceAssessment`, and `InvestigationReport` schemas.
- [ ] Define `published_at`, `disseminated_at`, `first_observed_at`, `move_onset_at`, and retrospective-evidence semantics.
- [ ] Define claim-level confidence, primary-hypothesis confidence, and completeness independently.
- [ ] Define provider success, empty result, partial result, retryable failure, permanent failure, and permission failure.
- [ ] Define a field-aware disagreement matrix for price, volume, corporate action, issuer fact, timestamp, FX, and market interpretation.
- [ ] Approve one primary and one fallback path for every launch-critical capability. A capability without an approved source is removed from launch scope or causes an explicit incomplete-data result.
- [ ] Define the human gold-label workflow, including two independent labels and adjudication for disputed causal attribution.
- [ ] Create the root project package and CI skeleton without importing upstream trading-agent architecture.

### Gate M0

M0 passes when:

- Every launch data field has an owner, source policy, timestamp policy, and failure behavior.
- The canonical JSON schema can represent all required outputs without relying on prose.
- A reviewer can explain exactly what a displayed confidence value means.
- The sentinel manifest includes AEST/AEDT boundaries, ASX holidays, early closes, non-trading dates, after-close announcements, ex-dividend moves, ticker changes, trading halts, provider failures, and conflicting sources.
- No unresolved architecture decision blocks Phase 1.

## 6. Phase 1: ASX Domain Truth Layer

**Milestone:** M1

**Purpose:** Make instrument identity, session timing, currency, and corporate-action semantics trustworthy before adding inference.

### Primary files

- `src/asx_investigator/domain/models.py`
- `src/asx_investigator/domain/enums.py`
- `src/asx_investigator/providers/protocols.py`
- `src/asx_investigator/providers/errors.py`
- `src/asx_investigator/market/instruments.py`
- `src/asx_investigator/market/sessions.py`
- `src/asx_investigator/market/currency.py`
- `src/asx_investigator/market/corporate_actions.py`
- `tests/unit/domain/`
- `tests/unit/market/test_sessions.py`
- `tests/unit/market/test_currency.py`
- `tests/unit/market/test_corporate_actions.py`

### Work packages

- [ ] Implement point-in-time instrument resolution, including historical ticker and name changes.
- [ ] Implement an ASX calendar adapter with historical AEST/AEDT conversion and date-specific session phases.
- [ ] Represent regular sessions, early closes, non-trading dates, suspensions, halts, and missing calendar coverage distinctly.
- [ ] Implement `MonetaryValue` conversion with immutable FX provenance.
- [ ] Implement corporate-action normalization for dividends, splits, consolidations, rights issues, placements, and known index events where approved data exists.
- [ ] Add contract tests that every provider raises typed errors instead of returning false empty results.

### Gate M1

M1 passes when:

- All sentinel calendar and timezone cases pass.
- No naive datetime crosses a domain or provider boundary.
- A non-trading date is never silently remapped.
- Corporate-action tests distinguish mechanical price changes from informational moves.
- Currency round-trip tests preserve the original amount and provenance while rendering the AUD amount correctly.
- Provider contract tests prove failure and genuine absence are distinguishable.

## 7. Phase 2: Market Forensics

**Milestone:** M2

**Purpose:** Establish what moved, when it moved, and how much remained after relevant controls.

### Primary files

- `src/asx_investigator/market/returns.py`
- `src/asx_investigator/market/anomaly.py`
- `src/asx_investigator/market/peers.py`
- `src/asx_investigator/market/factors.py`
- `src/asx_investigator/market/event_study.py`
- `src/asx_investigator/market/forensics.py`
- `tests/unit/market/test_returns.py`
- `tests/unit/market/test_anomaly.py`
- `tests/unit/market/test_factors.py`
- `tests/unit/market/test_event_study.py`
- `tests/regression/market_reference_cases/`

### Work packages

- [ ] Define adjusted and unadjusted price use for each calculation.
- [ ] Calculate close return, open gap, open-to-close return, intraday range, volume z-score, turnover in AUD, and realized volatility.
- [ ] Detect unusual movement from return, residual, gap, volume, and liquidity features without treating the anomaly score as causal confidence.
- [ ] Build point-in-time peer and sector baskets with recorded membership and weighting rules.
- [ ] Implement factor controls with explicit availability checks and collinearity diagnostics.
- [ ] Adapt only the useful event-study concepts from `third_party/ai-hedge-fund`; remove SPY, US filing, fixed-date, and earnings-only assumptions.
- [ ] Estimate price-move onset from intraday bars when available and lower causal resolution when only daily data exists.
- [ ] Label residuals as model-unexplained returns, not direct causal contribution.

### Gate M2

M2 passes when:

- Hand-calculated reference cases match the implementation within documented numeric tolerances.
- Event windows use ASX sessions rather than calendar-day offsets.
- Ex-dividend and split cases do not generate false informational anomalies.
- Factor outputs expose observations, coefficients, residual variance, diagnostics, and missing-factor warnings.
- A result cannot claim intraday timing precision when the provider supplied only daily bars.
- The same recorded inputs produce byte-stable structured market outputs.

## 8. Phase 3: Evidence and Context System

**Milestone:** M3

**Purpose:** Turn source documents into a reproducible evidence set with exact provenance and bounded model context.

### Primary files

- `src/asx_investigator/evidence/models.py`
- `src/asx_investigator/evidence/snapshots.py`
- `src/asx_investigator/evidence/parsing.py`
- `src/asx_investigator/evidence/retrieval.py`
- `src/asx_investigator/evidence/registry.py`
- `src/asx_investigator/evidence/dedup.py`
- `src/asx_investigator/evidence/conflicts.py`
- `src/asx_investigator/evidence/citations.py`
- `tests/unit/evidence/`
- `tests/integration/providers/`
- `evals/fixtures/documents/`

### Work packages

- [ ] Implement approved disclosure, market-context, corporate-action, and news adapters behind the Phase 0 protocols.
- [ ] Save immutable source snapshots with retrieval time, response metadata, content hash, and provider identity.
- [ ] Extract text and tables with page, block, character, and PDF bounding-box locators where available.
- [ ] Classify evidence as causal input, contemporaneous reaction, retrospective context, or excluded.
- [ ] Filter by instrument, date, document type, price-sensitive flag, and temporal eligibility before full-text retrieval.
- [ ] Implement bounded hybrid retrieval using lexical score, semantic score, metadata prior, and hypothesis terms.
- [ ] Deduplicate exact copies, near copies, syndication, and shared quoted origins before counting corroboration.
- [ ] Preserve unresolved conflicts and apply the field-aware source policy without rewriting source values.
- [ ] Treat retrieved documents as untrusted data and test prompt-injection isolation.

### Gate M3

M3 passes when:

- Every evidence item can open the exact frozen source passage used by the system.
- Recorded retrieval produces the same evidence IDs and hashes across runs.
- Primary-source Recall@10 is at least 0.95 on the development evidence set.
- Syndicated copies do not increase independent-corroboration counts.
- Post-move evidence cannot become causal input.
- Provider outages produce incomplete coverage, not a false no-evidence conclusion.
- Source-document instructions cannot alter system behavior or tool routing.

## 9. Phase 4: Investigation Graph and Claim Construction

**Milestone:** M4

**Purpose:** Build the smallest reasoning workflow that can generate, challenge, and support causal explanations.

### Primary files

- `src/asx_investigator/investigation/state.py`
- `src/asx_investigator/investigation/graph.py`
- `src/asx_investigator/investigation/routing.py`
- `src/asx_investigator/investigation/investigator.py`
- `src/asx_investigator/investigation/validator.py`
- `src/asx_investigator/investigation/critic.py`
- `src/asx_investigator/investigation/claims.py`
- `src/asx_investigator/investigation/prompts/`
- `tests/unit/investigation/`
- `tests/integration/test_investigation_graph.py`

### Work packages

- [ ] Implement one serializable `InvestigationState` shared by all nodes.
- [ ] Generate a bounded set of materially different hypotheses covering company information, mechanical effects, sector or macro factors, flows or liquidity, and no identifiable catalyst.
- [ ] Require each hypothesis to state direction, expected market signature, validation requirements, supporting evidence, and contradicting evidence.
- [ ] Run temporal, direction, magnitude, peer, sector, factor, mechanical, and source-authority checks outside the model.
- [ ] Allow one bounded targeted-retrieval loop when the critic identifies a specific missing item.
- [ ] Use one critic node to search for timing leakage, unsupported assumptions, source conflicts, and stronger alternatives.
- [ ] Build typed claims classified as `CAUSE`, `CONTRIBUTOR`, `CONTEXT`, `MECHANICAL`, `FACT`, or `UNRESOLVED`.
- [ ] Reject any material claim that has no registered support.

### Gate M4

M4 passes when:

- Recorded end-to-end cases complete without free-form prose becoming program state.
- Every material claim has support IDs and every contradiction is retained.
- The graph terminates under fixed retrieval and retry budgets.
- After-close and post-move adversarial cases produce zero causal timing violations.
- Mechanical and sector explanations remain distinct from company-specific causes.
- The agent can return no identifiable catalyst without inventing a narrative.

## 10. Phase 5: Confidence, Calibration, and Abstention

**Milestone:** M5

**Purpose:** Convert observable investigation quality into confidence values that can be tested.

### Primary files

- `src/asx_investigator/confidence/features.py`
- `src/asx_investigator/confidence/rules.py`
- `src/asx_investigator/confidence/calibrator.py`
- `src/asx_investigator/confidence/abstention.py`
- `src/asx_investigator/confidence/artifacts.py`
- `tests/unit/confidence/`
- `evals/calibration/`

### Work packages

- [ ] Compute raw features for source authority, temporal alignment, market-signature fit, quantitative consistency, independent corroboration, contradiction strength, alternative strength, and source coverage.
- [ ] Define deterministic confidence caps for missing primary evidence, weak sources, unresolved conflicts, missing intraday data, and incomplete retrieval.
- [ ] Keep claim confidence, selected-hypothesis confidence, and completeness separate in storage and presentation.
- [ ] Fit the selected calibration method only on the calibration split and store its dataset version, feature version, code version, and metrics.
- [ ] Implement abstention thresholds against selective accuracy and coverage rather than a fixed desire to answer every case.
- [ ] Return conservative bands instead of precise percentages when the calibration sample is too small for stable probability estimates.

### Gate M5

M5 passes when:

- Removing or contradicting evidence changes only the documented confidence features and dependent claims.
- Structurally weak evidence cannot produce high confidence.
- Calibration beats the uncalibrated score on held-out Brier score and does not worsen selective accuracy.
- Reliability results include sample counts and bootstrap intervals, not only ECE.
- The abstention policy is frozen before the blind holdout is opened.
- Calibration artifacts cannot load against an incompatible feature schema.

## 11. Phase 6: Evaluation Harness and Blind Results

**Milestone:** M6

**Purpose:** Prove that the system retrieves the right evidence, avoids temporal leakage, supports its claims, ranks causes correctly, and knows when to stop.

### Primary files

- `evals/cases/`
- `evals/fixtures/`
- `evals/gold/`
- `evals/graders/retrieval.py`
- `evals/graders/attribution.py`
- `evals/graders/grounding.py`
- `evals/graders/temporal.py`
- `evals/graders/calibration.py`
- `evals/run.py`
- `evals/reports/render.py`
- `tests/regression/eval_cases/`

### Dataset policy

- Development, calibration, and blind-holdout cases are separated by time and issuer where possible.
- Each gold case records primary driver, secondary drivers, acceptable alternatives, evidence, prohibited future evidence, ambiguity, and abstention acceptability.
- Human causal labels require two independent reviews and adjudication when they disagree.
- Recorded fixtures are immutable. Any correction creates a new dataset version.
- Live retrieval metrics are reported separately and never replace the recorded blind result.

### Work packages

- [ ] Build deterministic unit and property tests for time, calendar, corporate actions, FX, return math, event windows, provider failure, and citation integrity.
- [ ] Build mocked integration tests for tool routing, retry budgets, structured outputs, and incomplete-data behavior.
- [ ] Build the labeled historical dataset across disclosure, mechanical, sector, macro, commodity, flow, multi-catalyst, ambiguous, and no-catalyst cases.
- [ ] Add adversarial cases for after-close announcements, recycled news, ticker ambiguity, dual listings, trading halts, placements, index rebalances, source conflicts, and currency errors.
- [ ] Report retrieval, attribution, grounding, temporal integrity, abstention, calibration, latency, and cost independently.
- [ ] Run a simple deterministic or retrieval-only baseline so model gains are measurable.
- [ ] Seal the holdout before final prompt, score, cap, and threshold changes.
- [ ] Publish aggregate results and at least five failure analyses linked to traces.

### Initial release gates

| Metric | Gate |
|---|---:|
| Lookahead violation rate | 0.00 |
| Incorrect session attribution rate | 0.00 |
| Citation precision | >= 0.98 |
| Material unsupported claim rate | <= 0.01 |
| Primary-source Recall@10 | >= 0.95 |
| Primary-driver accuracy | >= 0.80 |
| Top-2 driver recall | >= 0.90 |
| Abstention precision | >= 0.85 |
| Calibrated Brier score | Better than frozen uncalibrated baseline |
| ECE | <= 0.08, reported with bin counts and uncertainty |

These gates are launch criteria, not claims about current performance. If the blind set is too small for a stable metric, the report must state that limitation and the UI must avoid false precision.

### Gate M6

M6 passes when:

- The blind run is reproducible from a clean environment.
- All hard temporal and citation gates pass.
- Calibration and attribution gates pass or the release scope is reduced and re-evaluated without opening new holdout labels.
- Every failure is classified as data, retrieval, temporal, quantitative, reasoning, grounding, calibration, or infrastructure.
- The final evaluation report includes dataset version, code version, model configuration, source mode, cost, and latency.

## 12. Phase 7: Working Agent Delivery

**Milestone:** M7

**Purpose:** Package the evaluated core as the required working agent.

### Primary files

- `src/asx_investigator/api/app.py`
- `src/asx_investigator/api/routes.py`
- `src/asx_investigator/api/schemas.py`
- `src/asx_investigator/report/validator.py`
- `src/asx_investigator/report/markdown.py`
- `src/asx_investigator/report/json.py`
- `src/asx_investigator/storage/cases.py`
- `src/asx_investigator/storage/traces.py`
- `src/asx_investigator/cli.py`
- `README.md`
- `Dockerfile`

### Work packages

- [ ] Expose `POST /v1/investigations` with a versioned request and response contract.
- [ ] Provide a CLI that runs the same service path as the API.
- [ ] Render JSON and Markdown from the validated claim-evidence graph.
- [ ] Validate citation existence, semantic support, numeric consistency, timing, ticker relevance, and duplicate-origin inflation before release.
- [ ] Store immutable completed case versions, traces, provider metadata, source hashes, model configuration, and calibration version.
- [ ] Support `LIVE` mode for current provider calls and `RECORDED` mode for stable demonstrations and evaluation.
- [ ] Document local setup, provider requirements, supported scope, known limits, and exact evaluation commands.
- [ ] Produce the required short rationale for tools, context management, memory, and evaluation.

### Gate M7

M7 passes when:

- A clean checkout can run one recorded case and produce the expected JSON, Markdown, and trace.
- A configured environment can run a live historical investigation or return an explicit provider limitation.
- API and CLI results are schema-equivalent.
- No final material claim bypasses the citation validator.
- The deliverable contains the working agent, evaluation harness, evaluation results, and four-decision rationale.

## 13. Phase 8: Minimal Investigation Workbench

**Milestone:** M8

**Purpose:** Expose the proof layer required for human inspection without building every proposed product surface.

### Launch UI scope

- New investigation form.
- Case header with instrument, date, timezone, status, and confidence.
- Market move summary and price chart.
- Primary assessment and competing hypotheses.
- Event timeline with temporal eligibility.
- Evidence list and source-passage viewer.
- Quantitative validation details.
- Confidence explanation.
- Markdown report and basic trace.

The evidence graph, command palette, advanced counterfactuals, collaboration, mobile authoring, and full evaluation administration remain deferred.

### Work packages

- [ ] Derive a typed frontend client from the canonical API schema.
- [ ] Render structured case state without parsing chat prose.
- [ ] Make citations open the exact registered passage.
- [ ] Show incomplete data, conflicts, exclusions, and preliminary states explicitly.
- [ ] Provide keyboard access, visible focus, text alternatives for charts, non-color state labels, and WCAG 2.1 AA checks.
- [ ] Keep conversational refinements as typed case mutations that create a new case version.

### Gate M8

M8 passes when:

- A user can answer what moved, why, based on what evidence, what alternatives remain, and why confidence has its value from one case view.
- Chat and structured surfaces read and update the same case state.
- Excluding evidence or changing the time cutoff produces a versioned rerun and visible confidence change.
- Accessibility checks pass for the supported desktop workflow.
- The UI introduces no financial fact that is absent from the API response.

## 14. Phase 9: Release Hardening

**Milestone:** M9

**Purpose:** Make the evaluated workbench safe to operate and easy to diagnose.

### Work packages

- [ ] Add structured logging, OpenTelemetry traces, provider health, latency, cost, cache, and model-usage measurements.
- [ ] Add request timeouts, bounded retries, rate limits, MIME checks, file-size limits, safe HTML handling, and URL policy.
- [ ] Keep secrets, raw provider payloads, prompts, user data, and public traces separated.
- [ ] Add dependency, license, secret, and container scans to CI.
- [ ] Run load, provider-outage, corrupted-document, model-timeout, and storage-recovery tests.
- [ ] Freeze data retention, case deletion, audit retention, and access-control policy before multi-user deployment.
- [ ] Produce a release evidence pack containing test results, evaluation results, known limitations, runbooks, and rollback steps.

### Gate M9

M9 passes when:

- CI passes lint, type checking, unit tests, integration tests, recorded eval smoke tests, schema compatibility, and security scans.
- Nightly or manual evaluation detects regression in accuracy, grounding, timing, calibration, latency, and cost.
- Provider outages degrade to partial or incomplete results without producing fabricated certainty.
- A release can be reproduced, rolled back, and traced to source, model, prompt, data, and calibration versions.

## 15. Cross-Cutting Engineering Rules

### 15.1 Test-first implementation

Each phase-level execution plan must split work into reviewable tasks. Each behavior starts with a failing test, adds the smallest implementation, passes the focused test, passes the related suite, and then commits. Milestone checkboxes are not substitutes for task-level tests.

### 15.2 Structured state

Free-form prose never becomes routing or scoring state. Model nodes emit Pydantic-constrained outputs. The report renderer is the only place where longer prose is created.

### 15.3 Reproducibility

Every case records:

- Code revision.
- Schema version.
- Provider and dataset versions.
- Source hashes and retrieval times.
- Calendar and instrument-reference versions.
- Model provider, model name, parameters, and prompt version.
- Confidence-feature and calibration-artifact versions.
- Tool inputs, outputs, errors, cache status, latency, token use, and cost.

### 15.4 Memory boundaries

Case state remains inside the case. Persistent storage may contain stable identifiers, source schemas, calendar metadata, retrieval statistics, provider reliability observations, and calibration artifacts. Previous causal narratives, rumors, and model conclusions never become silent priors for a new investigation.

### 15.5 Change control

Changes to time eligibility, source precedence, label policy, confidence features, confidence caps, abstention thresholds, or evaluation splits require an ADR and a new artifact version. Changes made after blind-holdout review require a new sealed holdout before a release claim.

## 16. Critical Risks and Controls

| Risk | Control | Milestone owner |
|---|---|---|
| Data licensing or historical coverage blocks a provider | Approve the provider matrix before adapter work; reduce scope explicitly when coverage cannot be licensed | M0 |
| Historical timestamps do not prove when the market saw information | Store multiple timestamp meanings and cap or reject causal eligibility when dissemination is uncertain | M1, M3 |
| Corporate actions create false anomalies | Use unadjusted prices and explicit mechanical-event checks before narrative reasoning | M1, M2 |
| Factor residual is presented as causal attribution | Label it model-unexplained and require separate evidence for the causal claim | M2, M4 |
| Retrieval misses the decisive disclosure | Track gold-evidence recall and block M3 below the threshold | M3 |
| Duplicate news appears to corroborate itself | Cluster by origin, content, syndication, and quoted source | M3 |
| LLM invents a supported-looking claim | Constrained outputs plus claim and citation validation | M4, M7 |
| Confidence is precise but uncalibrated | Separate scores, caps, calibration artifacts, uncertainty, and abstention | M5, M6 |
| Evaluation leaks issuer or event patterns | Time and issuer separation, sealed holdout, immutable fixtures | M6 |
| UI scope delays the working agent | M7 is the assignment-complete gate; UI begins afterward | M7, M8 |

## 17. Project Definition of Done

The project is complete when all of the following are true:

- [ ] A user can submit an unseen supported ASX equity and historical ASX date.
- [ ] The system resolves the correct instrument, timezone, calendar, and session.
- [ ] It measures the move and states whether the move is unusual.
- [ ] It retrieves point-in-time evidence and records source coverage and failures.
- [ ] It evaluates company-specific, mechanical, sector, macro, flow, and no-catalyst explanations as applicable.
- [ ] It preserves alternative explanations and contradictions.
- [ ] Every material claim has valid evidence or quantitative-result links.
- [ ] Confidence values have defined targets, caps, calibration versions, and empirical results.
- [ ] The system abstains when the evidence or data coverage is insufficient.
- [ ] All figures render in AUD and all timestamps render in AEST or AEDT.
- [ ] Recorded evaluation is reproducible and the blind results meet the release gates.
- [ ] The repository includes the working agent, eval harness, results, rationale, setup instructions, and known limitations.

## 18. Immediate Next Action

Create the Phase 0 execution plan and complete M0 before implementing providers, LangGraph nodes, prompts, or frontend components. The first accepted artifact is the canonical contract set, because every later module depends on its definitions of time, evidence, confidence, source failure, and evaluation truth.
