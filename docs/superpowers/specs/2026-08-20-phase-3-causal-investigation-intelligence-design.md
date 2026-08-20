# Phase 3: Causal Investigation Intelligence

**Status:** Implemented design reference; Phase 3 external release gates OPEN (`NOT_RUN`)
**Date:** 20 August 2026
**Current baseline:** Phase 3 recorded release candidate
**Primary decision:** Build a causal investigation kernel, not a general multi-agent platform

## Purpose

The recorded release candidate can run an investigation, preserve evidence and provider artifacts, recover from durable checkpoints, and publish a cited explanation with an evidence-strength band. It has not established real-case attribution accuracy. Its development suite is synthetic; frozen gold bundles execute through the production path, but the external development corpus, sealed holdout and credentialed Live gates remain `NOT_RUN`.

Phase 3 turns that baseline into a reliable investigation agent for unseen ASX cases. The work centers on three things: a better causal reasoning contract, explicit memory boundaries, and an evaluation loop that runs the production path against adjudicated point-in-time evidence.

## Product outcome

Given an ASX ticker and trading date, the product must:

1. establish the session and observed move in AUD;
2. test mechanical and market-context explanations before causal synthesis;
3. build ranked causal hypotheses from frozen evidence assertions;
4. challenge the leading hypothesis and record unresolved alternatives;
5. compile every published material claim from validated evidence;
6. expose why it answered, abstained, or reported incomplete data;
7. produce a trace that can be replayed and graded without hidden state.

An unseen case is successful when the agent either identifies an acceptable driver with valid citations or abstains for a reason allowed by the case policy. A fluent unsupported answer is a failure.

## Architectural choice

The runtime remains one typed orchestrator with two bounded model roles. It does not become a group-chat system and it does not give the model direct provider access.

```text
Case request
  -> session and instrument truth
  -> market and mechanical facts
  -> frozen document acquisition
  -> exact evidence assertions
  -> deterministic mechanism tests
  -> ranked causal hypotheses                [Gemini call 1]
  -> one explicit evidence-gap retrieval
  -> adversarial challenge and selection     [Gemini call 2]
  -> deterministic claim compiler
  -> confidence, calibration status and abstention
  -> immutable investigation ledger
  -> report and evaluation record
```

This structure keeps the useful parts of an agent: hypothesis formation, targeted inquiry and adversarial review. Facts, source eligibility, calculations, citations, confidence rules and publication remain code-owned.

## Investigation kernel

The current service coordinates the full pipeline in one large unit. Phase 3 introduces an `InvestigationKernel` whose stages exchange typed values. The kernel owns ordering, budgets, checkpoints and terminal outcomes. It does not own provider implementations, document parsing, confidence rules or report presentation.

The central state is an append-only `InvestigationLedger`. Each entry records the stage, input hashes, output hashes, policy versions, model configuration, validation result and timestamp. Checkpoint state remains the recovery format. The ledger is the audit format. Neither is used as model memory outside the current case version.

The kernel runs a fixed set of causal mechanism tests:

- `MECHANICAL`: split, consolidation, distribution, capital reconstruction or symbol change;
- `ISSUER_EVENT`: guidance, earnings, operations, financing, transaction or governance event;
- `SECTOR_READTHROUGH`: a time-eligible event affecting comparable issuers;
- `COMMODITY_FX`: a relevant commodity or currency move with a documented issuer exposure;
- `MACRO_MARKET`: rates, policy, index or broad risk event;
- `MARKET_STRUCTURE`: liquidity, index rebalance or other non-fundamental trading mechanism;
- `UNKNOWN`: no hypothesis clears the evidence and validation rules.

The mechanism taxonomy is versioned. It is small enough to test and broad enough for the target product. New mechanisms require a schema change, a deterministic signature test and evaluation cases.

## Evidence assertions and claim compilation

Long documents remain outside the model context. The evidence pipeline continues to freeze source bytes, segment exact passages and retrieve with SQLite FTS5 plus metadata filters. Phase 3 adds a typed assertion layer between passages and hypotheses.

An `EvidenceAssertion` contains:

- a case-scoped assertion ID;
- the exact source passage or bounded extractive span;
- evidence ID, locator, span hash and artifact hash;
- publication and retrieval time;
- authority and evidence role;
- normalized entities, dates and numeric values extracted by deterministic code where possible;
- causal eligibility for the selected session;
- contradiction links.

The first Gemini role may rank hypotheses only by referencing allowed assertion IDs. It may name an evidence gap, expected market signature and falsifier. It cannot write a publishable claim.

The second role receives an ID-only challenge view of the ranked batch and the final bounded packet. The first model's prose is untrusted and is never forwarded. It may select an existing hypothesis, choose a supplied alternative, accept eligible targeted assertions, or reject all candidates. It cannot add a mechanism, change evidence timing or introduce an unknown ID.

The claim compiler is deterministic. It renders the chosen mechanism and exact supported assertions into the report schema. Model prose remains available in the internal trace for diagnosis, but it cannot become the text of a material claim. Numeric and entity checks run before publication. A failed compiler or validation rule produces `INSUFFICIENT_EVIDENCE`.

## Tool design

Tools remain typed, narrow and auditable:

| Tool boundary | Responsibility | Publication authority |
|---|---|---|
| Instrument and session | ASX identity, calendar and AEST/AEDT session | Factual |
| Market truth | EOD bars, benchmark, sector and volume facts | Factual after reconciliation |
| Corporate actions | Effective mechanical events | Causal when time-eligible |
| Discovery | Find candidate issuer and official material | Discovery only |
| Frozen source | Fetch, hash, parse and locate approved material | Depends on source policy |
| Market context | Commodity, FX, rates and broad-market facts | Context unless issuer exposure is documented |
| Evidence retrieval | Return bounded assertions under case filters | No authority beyond stored source role |

EODHD remains the primary price source and Marketstack the fallback. Prices are not mixed when the primary result is complete. Material disagreement is preserved as a conflict set and caps confidence. Values are never averaged to hide a conflict.

Discovery results do not become causal evidence. An issuer release, approved official source or explicitly supplied official document must be frozen before it can support a causal claim. Document text is untrusted data at every model boundary.

## Context management

Each model call receives a `ReasoningPacket`, not a raw case archive. The packet contains:

- market and mechanism-test facts;
- at most 12 exact evidence assertions;
- coverage gaps and material conflicts;
- allowed assertion and evidence IDs;
- source authority and timing classification;
- the current hypothesis contract;
- explicit instruction that source text is untrusted.

Selection follows deterministic priority: causal eligibility, authority, contradiction value, query relevance and stable source order. A targeted retrieval rebuilds the packet under the same cutoff, exclusion and primary-source policy. It does not bypass the initial filters.

The model never receives prior case claims, prior model summaries, sealed labels, hidden gold alternatives, provider credentials or raw binary documents.

## Memory model

Memory is split by purpose. Each layer has a different lifetime and admission rule.

### Run memory

Run memory is the typed kernel state for one case version. It includes market facts, evidence assertions, hypothesis state, model outputs, validation results and checkpoints. It survives restart and is discarded from active memory when the version terminates. The immutable version remains available for audit.

### Case memory

Case memory contains the append-only ledger, frozen artifacts, evidence registry, report and version lineage for one case. A refinement creates a child version. The child may inherit explicitly selected source artifacts and request fields. It does not receive the parent's causal conclusion or model summary as input.

### Shared product memory

Only four classes may cross case boundaries:

1. versioned ASX calendar and source-policy rules;
2. provider health, schema compatibility and TTL cache metadata;
3. issuer reference facts such as identity, sector and listing metadata, each with provenance, validity range and expiry;
4. reviewed calibration artifacts produced by the offline evaluation process.

Issuer reference facts are `CONTEXT_ONLY`. They cannot support a causal claim without case evidence. Provider health can change routing but cannot change facts. Calibration artifacts can change a confidence rule only through a reviewed versioned release.

The following are prohibited shared memory:

- historical claims, hypotheses and summaries;
- ticker-specific causal priors;
- model-generated issuer profiles;
- user-uploaded case documents outside their allowed case lineage;
- development gold labels at runtime;
- sealed holdout labels anywhere in production context.

There is no automatic cross-case learning. Evaluation failures produce reviewed code, policy or calibration changes.

## Confidence and calibration

Confidence remains `LOW`, `MEDIUM` or `HIGH`. It is not a probability. Phase 3 adds empirical calibration metadata without changing that language.

The selected-hypothesis band, each claim's support band and investigation completeness remain separate. Confidence features include source authority, temporal eligibility, mechanism signature fit, numeric consistency, independent corroboration, contradiction strength, alternative strength, disclosure coverage and provider conflict.

The evaluation pipeline records, per band, the number of correct, acceptable-alternative, abstained and materially wrong outcomes. A calibration artifact contains the corpus version, rule version, raw counts, observed proportions and creation commit. It is marked `INSUFFICIENT_SAMPLE` when a band has fewer than five eligible cases. Holdout results never tune the rule that they evaluate.

`HIGH` remains capped or disabled when primary evidence, time resolution or required coverage is missing. A materially wrong `HIGH` explanation is a release-blocking failure.

## Evaluation architecture

Phase 3 keeps the synthetic suite for fast policy regression and adds production-path gold evaluation.

### Corpus layers

1. `Synthetic regression`: deterministic fixtures for contracts, failures and adversarial behavior.
2. `Gold development`: 24 real point-in-time cases used for debugging and reviewed rule changes.
3. `Sealed holdout`: exactly 12 issuer- and time-isolated cases stored outside the repository.
4. `Unseen review run`: the same sealed execution interface used by an evaluator to add a case the team has never seen.

The 24 development cases should cover issuer disclosures, mechanical events, commodity or FX drivers, sector or market read-through, macro events, multi-catalyst moves, ambiguous moves and valid no-catalyst outcomes. One preparer freezes the case bundle and proposes labels. A second reviewer checks the cutoff, primary evidence, acceptable alternatives and abstention policy before the case becomes gold.

### Frozen case bundle

Each real case contains a manifest, raw artifact hashes, normalized provider responses, source documents and expected market facts with tolerances. The runner constructs recorded providers from those artifacts and executes the normal `InvestigationKernel`. It does not grade a prebuilt report supplied by the case fixture.

Holdout labels remain outside the repository under `ASX_EVAL_HOLDOUT_ROOT`. The production package can generate a blind report bundle but cannot load labels. The external grader joins reports to labels after execution.

### Graders

Deterministic graders own:

- ASX session and AEST/AEDT correctness;
- market calculations and AUD normalization;
- evidence cutoff and lookahead integrity;
- citation existence, source role and assertion-span integrity;
- top-1 and top-2 acceptable attribution;
- mechanical-event handling;
- required and false abstention;
- coverage and provider-failure semantics;
- confidence caps and band monotonicity;
- artifact and trace reproducibility;
- latency and measured model cost.

A model judge may classify failure themes for diagnosis. It cannot change a score, label, band or release status.

### Release gates

Safety gates use zero tolerance:

- 0 lookahead violations;
- 0 incorrect session assignments;
- 0 missing citations on material claims;
- 0 published claims with unknown or ineligible support;
- 0 provider failures reported as no catalyst;
- 0 materially wrong `HIGH` explanations;
- 100 percent recorded artifact and trace reproducibility.

Behavior gates report raw numerators and denominators:

- top-1 acceptable attribution at least 75 percent on answerable cases;
- top-2 acceptable attribution at least 90 percent on answerable cases;
- 100 percent correct abstention on cases labelled `REQUIRED`;
- false abstention no more than 20 percent on answerable cases;
- all confidence caps covered by direct tests;
- per-band calibration status and sample count present in the report.

The thresholds are release rules, not claims of statistical certainty. A missing real corpus, holdout or credentialed Live run remains `NOT_RUN`.

## Failure and recovery behavior

Provider `EMPTY`, `PARTIAL`, `RETRYABLE_FAILURE` and `PERMANENT_FAILURE` outcomes remain distinct. A retry resumes only from a compatible checkpoint. An incompatible checkpoint creates an audited child version. A completed version is immutable.

Model timeout, invalid schema, unknown assertion ID, unsupported assumption, timing leakage or claim-compiler failure preserves market facts and returns `INSUFFICIENT_EVIDENCE`. Missing point-in-time market data returns `INCOMPLETE_DATA`. `NO_IDENTIFIABLE_CATALYST` requires complete required coverage and a completed search under the unfiltered case scope.

## Product surface

The English workbench adds an investigation ledger view, mechanism-test results, assertion-level citations, rejected-hypothesis reasons, calibration sample status and blind-evaluation export. It keeps lifecycle, outcome, confidence and completeness separate.

The interface does not expose model chain-of-thought, provider credentials, raw artifact bytes or sealed labels. It shows structured decisions, evidence, rules and trace metadata.

## Delivery sequence

Phase 3 is one product phase with seven gated milestones:

1. `P3.0 Contract and documentation reset`
2. `P3.1 Investigation kernel and ledger`
3. `P3.2 Evidence assertions and causal reasoning`
4. `P3.3 Memory admission and isolation`
5. `P3.4 Production-path gold evaluation`
6. `P3.5 Confidence calibration and release policy`
7. `P3.6 Live evidence completion and workbench release`

Each milestone uses test-first development, an independent review, a separate commit and synchronized documentation. Implemented milestone code and external release approval are reported separately: a missing external gate is `NOT_RUN`, never a release pass.

## Scope control

Phase 3 does not add authentication, collaboration, monitoring, alerts, trading recommendations, execution, a plugin marketplace, a vector database, a general knowledge graph, mobile authoring or autonomous cross-case learning.

The architecture may use small deterministic mechanism modules. It does not add autonomous specialist agents or a framework whose main purpose is agent-to-agent conversation.

## Documentation control

The following files must agree after every milestone:

- `MASTER_DEVELOPMENT_PLAN.md` for product state and sequence;
- the Phase 3 phase plan for milestone status;
- `design requirement document v1.md` for product behavior and interface state;
- `README.md` for runnable current capability and limits;
- evaluation methodology and result files for measured release evidence;
- architecture decision records for changes to source, memory, confidence or holdout policy.

Documentation status is checked in the milestone acceptance review. Planned features are labelled planned. Implemented features require test evidence. External gates use `PASS`, `FAIL` or `NOT_RUN` only.
