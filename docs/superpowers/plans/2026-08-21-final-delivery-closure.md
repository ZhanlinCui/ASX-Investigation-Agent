# ASX Investigation Agent Final Delivery Closure Implementation Plan

> **For implementation:** Use test-driven development task by task. Complete and commit one task only after its focused gate, full regression gate and review checkpoint pass.

**Goal:** Turn the safe recorded release candidate into a recall-complete, externally measured Live ASX investigation product without weakening evidence, memory or evaluation boundaries.

**Architecture:** Keep the single durable investigation kernel as the orchestrator. Add a deterministic, typed retrieval planner in front of the existing evidence packet, execute a small set of source-policy lanes in parallel, and retain only one model-requested follow-up retrieval. Search discovers candidates; governed code fetches, freezes, classifies and extracts approved primary material. Shared memory is an audited routing input only. The existing two Gemini calls rank and challenge assertion IDs; deterministic code continues to own market facts, temporal eligibility, claim compilation, confidence and release gates.

**Tech stack:** Python 3.12, FastAPI, Pydantic, SQLite/WAL/FTS5, httpx, Gemini structured output, EODHD, governed web discovery, React/Vite, pytest and pnpm.

## Non-negotiable constraints

- All user-facing money is AUD and all public timestamps use `Australia/Sydney` AEST/AEDT.
- ASX cash-market sessions remain deterministic and independently tested.
- Gemini receives no provider credentials, network capability, raw shared-memory values, confidence control or citation-minting capability.
- Search results remain `DISCOVERY_ONLY`; an approved frozen primary document is required for causal support.
- Maximum model work remains two structured calls. Maximum adaptive retrieval remains one bounded follow-up.
- Prior case claims, hypotheses, summaries and holdout labels never enter another case.
- Confidence remains ordinal `LOW`/`MEDIUM`/`HIGH`, not a probability.
- Missing external inputs are `NOT_RUN`; failed providers are not genuine empty coverage.

---

## Task 1: Freeze the retrieval-planning contract

**Milestone:** P5.1
**Files:**

- Create: `src/asx_investigator/investigation/planning.py`
- Modify: `src/asx_investigator/providers/protocols.py`
- Modify: `src/asx_investigator/investigation/checkpoints.py`
- Test: `tests/unit/investigation/test_retrieval_planning.py`
- Test: `tests/unit/test_phase3_contracts.py`

### Step 1: Write the contract tests

Add tests proving:

- plans use only the seven approved `DriverLane` values;
- task IDs and ranks are deterministic for equivalent input;
- total initial provider calls, per-lane results and document bytes are hard-bounded;
- every skipped lane contains a typed reason;
- there is exactly one optional follow-up budget;
- arbitrary tool names, queries longer than the bound and unknown source roles fail validation;
- checkpoint policy changes reject pre-Phase-5 planning state rather than replaying it silently.

Use the following public shape:

```python
class DriverLane(StrEnum):
    ISSUER_DISCLOSURE = "ISSUER_DISCLOSURE"
    CAPITAL_AND_CORPORATE_ACTION = "CAPITAL_AND_CORPORATE_ACTION"
    INDEX_REBALANCE = "INDEX_REBALANCE"
    SECTOR_AND_PEER = "SECTOR_AND_PEER"
    COMMODITY_FX_MACRO = "COMMODITY_FX_MACRO"
    ANALYST_EVENT = "ANALYST_EVENT"
    NO_CATALYST_CONTROL = "NO_CATALYST_CONTROL"


class RetrievalTask(BaseModel):
    task_id: str
    lane: DriverLane
    tool: Literal["DISCOVER", "FETCH_OFFICIAL", "MARKET_CONTEXT"]
    query: str
    purpose: str
    max_results: int = Field(ge=1, le=5)


class RetrievalPlan(BaseModel):
    policy_version: str
    tasks: list[RetrievalTask] = Field(max_length=10)
    skipped_lanes: dict[DriverLane, str]
    follow_up_calls_remaining: Literal[1]
```

### Step 2: Verify RED

Run:

```bash
../../.venv/bin/python -m pytest tests/unit/investigation/test_retrieval_planning.py tests/unit/test_phase3_contracts.py -v
```

Expected: failure because the Phase 5 contract and checkpoint field do not exist.

### Step 3: Implement the minimum domain and protocol boundary

Implement only immutable plan models, deterministic serialization/hashing, budget validation and a provider protocol that accepts a `RetrievalTask`. Do not call a provider in this task. Add `retrieval_plan` and `retrieval_results` to `InvestigationState`, bump checkpoint policy/schema versions and retain strict stage-lineage validation.

### Step 4: Verify and commit

Run focused tests, then:

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/ruff check src tests evals
git diff --check
git add src/asx_investigator/investigation/planning.py src/asx_investigator/providers/protocols.py src/asx_investigator/investigation/checkpoints.py tests/unit/investigation/test_retrieval_planning.py tests/unit/test_phase3_contracts.py
git commit -m "feat: define bounded investigation retrieval plans"
```

---

## Task 2: Implement deterministic driver-lane planning

**Milestone:** P5.1
**Files:**

- Modify: `src/asx_investigator/investigation/planning.py`
- Modify: `src/asx_investigator/investigation/kernel.py`
- Modify: `src/asx_investigator/investigation/ledger.py`
- Test: `tests/unit/investigation/test_retrieval_planning.py`
- Test: `tests/integration/test_phase3_kernel_recovery.py`

### Step 1: Write failing behaviour tests

Cover at least these inputs:

- a resource issuer with admitted `commodity_exposure` adds commodity/FX and sector/peer lanes;
- a large price/volume move always includes issuer and capital/corporate-action lanes;
- no issuer memory still produces a conservative issuer/index/sector plan;
- context values affect only task routing and never appear in queries, evidence, assertions, Gemini payloads or claims;
- resumed cases reuse the exact persisted plan hash rather than creating a new plan;
- plan and execution summaries enter the append-only ledger without raw query response bodies.

### Step 2: Implement `RetrievalPlanner`

```python
class RetrievalPlanner:
    policy_version = "retrieval-policy-v1"

    def build(
        self,
        *,
        instrument: InstrumentIdentity,
        session: TradingSession,
        move: MarketMove,
        context_facts: list[IssuerReferenceFact],
    ) -> RetrievalPlan:
        ...
```

Use deterministic rules, not an LLM, to select lanes. Values such as sector, industry, commodity exposure and currency exposure may select an approved query template but must never be interpolated as unconstrained instructions. Persist the plan before network execution.

### Step 3: Add a durable `plan_evidence_retrieval` stage

Insert the stage after mechanical testing and before discovery. Record input/output hashes and a safe public summary. Ensure incompatible prior checkpoints create a child recovery version using the existing policy path.

### Step 4: Verify and commit

Run the focused tests, full backend suite, Ruff and diff check. Commit:

```bash
git commit -m "feat: plan investigation evidence lanes deterministically"
```

---

## Task 3: Acquire and promote approved primary sources

**Milestone:** P5.2
**Files:**

- Create: `src/asx_investigator/providers/evidence.py`
- Create: `src/asx_investigator/evidence/source_policy.py`
- Modify: `src/asx_investigator/providers/live.py`
- Modify: `src/asx_investigator/evidence/ingestion.py`
- Modify: `src/asx_investigator/evidence/registry.py`
- Modify: `src/asx_investigator/settings.py`
- Test: `tests/unit/providers/test_live_evidence_planner.py`
- Test: `tests/unit/evidence/test_source_policy.py`
- Test: `tests/integration/test_source_api.py`

### Step 1: Write source-policy and egress RED tests

Prove that:

- discovery responses are frozen but always remain `DISCOVERY_ONLY`;
- only HTTPS public destinations with validated DNS and connected peers are fetched;
- redirects, MIME, size and timeout bounds apply on every hop;
- approved issuer IR and approved official index/macro domains can be promoted only after exact document capture and timestamp validation;
- social posts, aggregators, generic news rewrites and unverifiable broker commentary cannot become primary causal evidence;
- source disagreement creates a conflict set; values or claims are never averaged;
- missing publication time, after-close publication and retrospective retrieval cannot support the same-session move;
- every provider response has a typed `ProviderOutcome` and artifact reference.

### Step 2: Implement source policy

Create a versioned policy with explicit decisions:

```python
class SourceDecision(BaseModel):
    authority: Literal["PRIMARY", "APPROVED_OFFICIAL", "DISCOVERY_ONLY", "REJECTED"]
    evidence_role: EvidenceRole
    causal_eligible: bool
    reason_code: str
    policy_version: str
```

Issuer-owned investor-relations documents are preferred. Approved index-provider and government/central-bank sources may support their own event facts. Named original analyst research is admissible only when the original timestamped document is captured or supplied by the user; a news summary remains reaction/context. Keep ASX page scraping prohibited.

### Step 3: Execute bounded lane tasks

Replace the single hard-coded Live query with an executor that runs only tasks in the sealed plan, limits concurrency and total bytes, deduplicates by canonical content hash, and freezes every response before parsing. Use EODHD for entitled market/context series and the configured discovery provider only for candidate discovery.

### Step 4: Verify and commit

Run:

```bash
../../.venv/bin/python -m pytest tests/unit/providers/test_live_evidence_planner.py tests/unit/evidence/test_source_policy.py tests/integration/test_source_api.py -v
../../.venv/bin/python -m pytest -q
../../.venv/bin/ruff check src tests evals
git diff --check
```

Commit:

```bash
git commit -m "feat: acquire governed primary investigation evidence"
```

---

## Task 4: Integrate bounded retrieval and coverage semantics

**Milestone:** P5.2
**Files:**

- Modify: `src/asx_investigator/investigation/kernel.py`
- Modify: `src/asx_investigator/evidence/context.py`
- Modify: `src/asx_investigator/agent/reasoning.py`
- Modify: `src/asx_investigator/confidence/scoring.py`
- Test: `tests/integration/test_phase5_retrieval_loop.py`
- Test: `tests/integration/test_reasoning_abstention.py`
- Test: `tests/unit/test_confidence.py`

### Step 1: Write end-to-end RED cases

Include issuer guidance, index rebalance, commodity read-through, analyst-event-without-original, provider partial failure and genuine no-catalyst cases. Assert:

- the initial plan may execute several fixed lanes, but Gemini can request at most one follow-up;
- the follow-up must name one missing lane/purpose and is filtered through the same policy;
- excluded, post-cutoff, non-primary or unknown evidence cannot re-enter through follow-up;
- discovery-only evidence can change a coverage gap but cannot publish a cause;
- failed required lanes yield `INSUFFICIENT_EVIDENCE`/partial coverage, never `NO_IDENTIFIABLE_CATALYST`;
- no-identifiable-catalyst requires complete coverage across all applicable lanes;
- confidence caps distinguish retrieval completeness, primary-source support, timing resolution and material conflicts.

### Step 2: Implement the bounded loop

The flow becomes:

```text
market/mechanical facts
-> deterministic retrieval plan
-> bounded lane execution and official-source capture
-> assertion packet
-> Gemini ranked ID hypotheses
-> optional one gap-directed task
-> rebuilt packet
-> Gemini challenge
-> deterministic validation/claim/confidence/publication
```

No `while` loop is allowed. The executor must reject a second follow-up request and publish the remaining gap.

### Step 3: Verify recovery and replay

Crash after plan persistence, midway through lane execution and after follow-up capture. Confirm restart reuses completed artifacts and reproduces validated decisions/coverage while never replaying a paid model call across a completed checkpoint.

### Step 4: Verify and commit

Run focused, recovery, full backend, Ruff and diff gates. Commit:

```bash
git commit -m "feat: investigate across bounded evidence lanes"
```

---

## Task 5: Operationalise safe memory without causal leakage

**Milestone:** P5.3
**Files:**

- Create: `src/asx_investigator/storage/memory_service.py`
- Modify: `src/asx_investigator/storage/memory.py`
- Modify: `src/asx_investigator/api/app.py`
- Modify: `src/asx_investigator/providers/live.py`
- Test: `tests/integration/test_phase5_memory_operations.py`
- Test: `tests/integration/test_phase3_memory_isolation.py`
- Test: `tests/unit/storage/test_shared_memory.py`

### Step 1: Write admission and use-path RED tests

Prove that:

- issuer facts enter memory only from frozen approved official artifacts with `valid_from`, `valid_until`, source hash and policy version;
- provider health is recorded from every typed provider outcome and expires by TTL;
- health can select primary/fallback/circuit-breaker routing but is never copied into Gemini prompts or reports as a causal fact;
- issuer reference values select retrieval lanes only and cannot become evidence/assertions/claims;
- revocation and point-in-time queries work across weekends and historical cases;
- generic `put`, nested values, historical conclusions, model summaries, free-form fields and holdout content remain rejected;
- reviewed calibration artifacts cannot be activated from holdout execution or an unvalidated Pydantic instance.

### Step 2: Add the narrow operational service

```python
class OperationalMemoryService:
    async def admit_issuer_reference(self, snapshot: FrozenSourceSnapshot) -> list[SharedMemoryEntry]:
        ...

    async def observe_provider_outcome(self, outcome: ProviderOutcome[object]) -> None:
        ...

    async def retrieval_context(self, ticker: str, as_of: datetime) -> RetrievalContext:
        ...
```

Use deterministic parsers/allowlists for sector, industry, business description, commodity exposure, currency exposure and exchange. Do not model-extract or store causal prose.

### Step 3: Wire routing only

`CaseManager` loads a sealed `RetrievalContext`; the planner consumes it. The evidence packet retains only its existing count/boundary marker. Provider health affects routing before calls and stays out of claims/confidence except as an explicit coverage gap when a required provider is unavailable.

### Step 4: Verify and commit

Run memory isolation/adversarial tests first, then the full suite. Commit:

```bash
git commit -m "feat: operate audited non-causal product memory"
```

---

## Task 6: Build and audit the real point-in-time corpus

**Milestone:** P5.4
**Files:**

- Create: `evals/build_gold_bundle.py`
- Create: `evals/audit_gold_corpus.py`
- Modify: `src/asx_investigator/evaluation/bundles.py`
- Modify: `src/asx_investigator/evaluation/manifests.py`
- Modify: `evals/README.md`
- Test: `tests/unit/evaluation/test_corpus_authoring.py`
- Test: `tests/unit/evaluation/test_bundles.py`

### Step 1: Test the authoring boundary

The builder must:

- consume only frozen provider/document artifacts and a target evidence cutoff;
- reject mutable URLs without captured bytes, non-ASX sessions, future evidence and unknown policy versions;
- emit content-addressed bundle/manifest files without labels in runtime-visible holdout bundles;
- write human adjudication templates outside production package paths;
- make replacement, label injection or artifact mutation fail hash verification.

### Step 2: Implement the authoring and audit CLIs

Commands:

```bash
.venv/bin/python evals/build_gold_bundle.py --case-spec /secure/dev-case.json --output-root "$ASX_EVAL_DEVELOPMENT_ROOT"
.venv/bin/python evals/audit_gold_corpus.py --kind development --root "$ASX_EVAL_DEVELOPMENT_ROOT"
.venv/bin/python evals/audit_gold_corpus.py --kind holdout --root "$ASX_EVAL_HOLDOUT_ROOT"
```

The audit prints counts by issuer, date, driver lane, abstention policy, source authority and coverage status. It fails if development has fewer than 24 cases, holdout fewer than 12, any issuer/date overlaps across splits, or required-abstention cases have a zero denominator.

### Step 3: Assemble the development distribution

The 24 development cases must cover at least:

- six issuer disclosure/guidance cases;
- three corporate action/capital-markets cases;
- three index/rebalance cases;
- four commodity/FX/macro cases;
- three sector/peer cases;
- two analyst/original-research cases;
- three no-catalyst, incomplete-data or required-abstention cases.

Select multiple market-cap tiers and sectors. Freeze all source bytes point-in-time. Do not reuse the synthetic `development_suite.json` as accuracy evidence.

### Step 4: Verify and commit tooling only

Corpus bytes and sealed labels remain outside the repository. Commit the authoring/audit code, examples with no labels or secrets, tests and documentation:

```bash
git commit -m "feat: author auditable point-in-time gold corpora"
```

---

## Task 7: Measure retrieval, attribution, abstention and ordinal calibration

**Milestones:** P5.4 and P5.5
**Files:**

- Modify: `src/asx_investigator/evaluation/grading.py`
- Modify: `src/asx_investigator/evaluation/gold.py`
- Modify: `src/asx_investigator/confidence/calibration.py`
- Modify: `evals/run_gold_evals.py`
- Create after actual execution: `evals/results/phase5-development-evaluation.md`
- Create after external grading: `evals/results/phase5-holdout-evaluation.md`
- Test: `tests/integration/test_phase5_release_gates.py`
- Test: `tests/integration/test_phase3_calibration_gate.py`

### Step 1: Add retrieval-quality RED tests

Separate acquisition from reasoning with deterministic metrics:

- applicable-lane execution coverage;
- gold primary-source discovery/acquisition within the evidence packet limit;
- temporal-eligibility precision;
- unsupported-source promotion count;
- top-1/top-2 on answerable explained cases;
- required/allowed/forbidden abstention outcomes;
- wrong-`HIGH`, citation, session, provider-failure and replay gates.

An answer cannot receive attribution credit when the required primary source never entered the packet. An abstention cannot inflate top-1/top-2 denominators.

### Step 2: Run and iterate on development only

Run:

```bash
.venv/bin/python evals/run_gold_evals.py --kind development --format markdown
```

Fix only failures visible in the development set. Record raw counts, denominators, per-case failure categories, retrieval recall, latency, measured AUD cost and all policy/model/pricing versions. After the development gate passes, freeze the retrieval policy, source policy and confidence rule hashes.

### Step 3: Run blind holdout once

Runtime generates label-free reports. A separately controlled grader reads labels and emits aggregates/failure IDs only. No holdout label or error-specific tuning enters production memory. If a hard gate or threshold fails, record `FAIL`; do not relabel or silently rerun.

### Step 4: Review ordinal confidence

Create a `ReviewedCalibrationArtifact` from development counts only, attach raw band counts and denominators, and show holdout performance as validation rather than a tuning input. Retain `UNCALIBRATED` unless the approved artifact and all required external gates exist. Never convert bands to empirical probabilities in this phase.

### Step 5: Verify and commit

Run all evaluation, adversarial and full project gates. Commit code separately from measured release records so results remain attributable:

```bash
git commit -m "feat: grade retrieval and causal release quality"
git commit -m "docs: record phase 5 external evaluation"
```

---

## Task 8: Finish the workbench and publish the release decision

**Milestone:** P5.6
**Files:**

- Modify: `src/asx_investigator/report/public.py`
- Modify: `src/asx_investigator/report/markdown.py`
- Modify: `src/asx_investigator/api/app.py`
- Modify: `web/src/App.tsx`
- Modify: `web/src/styles.css`
- Modify: `web/src/App.test.tsx`
- Modify: `README.md`
- Modify: `MASTER_DEVELOPMENT_PLAN.md`
- Modify: `design requirement document v1.md`
- Create: `docs/architecture-decisions/final-product-rationale.md`
- Create: `evals/results/final-release.md`
- Test: `tests/integration/test_phase3_report_api.py`
- Test: `tests/unit/report/test_markdown.py`

### Step 1: Write public-surface RED tests

The API, SSE, archive, versions, Markdown and static DOM must expose:

- the deterministic retrieval-plan lanes and safe completion/skipped reasons;
- source coverage and provider conflicts separate from hypothesis confidence;
- ranked validated hypotheses, mechanism tests, confidence factors/caps and completeness;
- controlled exact-passage links scoped by case version;
- external gate states and release status.

They must not expose raw provider bodies, arbitrary source URLs, secrets, memory values, model prompts/private prose, sealed labels or chain-of-thought. All timestamps must render in AEST/AEDT.

### Step 2: Implement compact workbench additions

Add one `Investigation plan` section and extend the existing coverage panel; do not create a new dashboard framework. Show each driver lane as `Complete`, `Partial`, `Failed` or `Skipped`, with the safe reason and source count. Preserve the warm research-desk visual system and keyboard access.

### Step 3: Write the required four-decision rationale

`docs/architecture-decisions/final-product-rationale.md` must explain:

1. tools, acquisition policy, precedence, fallback and conflict handling;
2. passage extraction, FTS filtering, packet bounds and prompt-injection treatment;
3. run/case/shared memory, TTL/revocation and prohibited cross-case state;
4. synthetic sentinels versus real development/holdout evaluation, release gates and ordinal calibration.

Keep it under 1,500 words and link directly to the relevant schemas, tests and release evidence.

### Step 4: Run credentialed final canaries

Run the EODHD-only provider smoke and at least three completed-session end-to-end Live cases representing issuer, context-driven and abstention outcomes. Store only safe aggregate metadata and artifact hashes. A provider entitlement gap remains visible and blocks release where required.

### Step 5: Run the final clean-checkout gate

From a new worktree with only documented environment variables:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q src
.venv/bin/ruff check src tests evals
.venv/bin/python evals/run_recorded_evals.py
.venv/bin/python evals/run_gold_evals.py --kind development --format markdown
pnpm --dir web test -- --run
pnpm --dir web build
git diff --check
```

Then run the sealed external grader and credentialed Live commands. Publish `PASS` only if every hard gate and required threshold passes. Otherwise publish the exact `FAIL`/`NOT_RUN` state and failure analysis.

### Step 6: Synchronise status and commit

Only after measured gates pass, change the master plan, README and product requirement from `recorded release candidate` to `release-approved`. Commit:

```bash
git commit -m "feat: complete the ASX investigation release workbench"
git commit -m "docs: publish final ASX investigation release evidence"
```

---

## Completion definition

Phase 5 is complete only when P5.1–P5.6 code gates pass and the real development, sealed holdout and credentialed Live results are present. Local unit tests, synthetic sentinels or a working UI alone cannot close the phase. If external inputs are absent, implementation may be reported as delivered, but final product release remains `OPEN (NOT_RUN)`.
