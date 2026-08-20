# Phase 3 Causal Investigation Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the recorded Phase 2.8 agent into an assertion-bound causal investigation system with isolated memory and production-path evaluation for unseen ASX cases.

**Architecture:** Keep one typed investigation orchestrator. Deterministic components acquire facts, build exact evidence assertions, run mechanism tests, compile claims and score confidence. Gemini is limited to a ranked hypothesis call and an adversarial challenge call over a bounded packet. Run and case state are immutable and durable; only versioned policy, provider health, issuer reference facts and offline calibration artifacts may cross cases.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite WAL and FTS5, FastAPI, Gemini structured output, React/TypeScript, pytest, Vitest.

## Global Constraints

- All monetary figures are AUD. User-facing timestamps use `Australia/Sydney` and show AEST or AEDT.
- Keep the ASX calendar, source precedence and provider failure semantics deterministic.
- Gemini makes at most two structured calls and cannot call providers, calculate market facts, set confidence or publish raw causal prose.
- A material claim must be compiled from registered, case-scoped, time-eligible evidence assertions.
- Do not add LangGraph, a vector database, general multi-agent chat, cross-case causal learning, authentication, alerts, trade recommendations or execution.
- Completed case versions, artifacts, checkpoints and ledger entries are immutable. Refinements remain child versions.
- Cross-case memory may contain only policy, provider health, issuer reference facts and reviewed calibration artifacts. It must never contain prior case claims, hypotheses, summaries, user documents or holdout labels.
- Gold development data and sealed holdout labels stay outside the repository. Missing external assets are `NOT_RUN`, never `PASS`.
- Every task uses test-first development, a focused test command, a full regression run before its commit, and synchronized English documentation.

---

## File structure

| Path | Responsibility |
|---|---|
| `src/asx_investigator/domain/models.py` | Public typed contracts for assertions, mechanisms, ledger entries, memory and calibration metadata. |
| `src/asx_investigator/investigation/assertions.py` | Build extractive, case-scoped assertions from frozen evidence. |
| `src/asx_investigator/investigation/mechanisms.py` | Deterministic mechanical, issuer, context and unknown mechanism tests. |
| `src/asx_investigator/investigation/ledger.py` | Append-only ledger construction and hash-safe summaries. |
| `src/asx_investigator/investigation/kernel.py` | Typed orchestration of the investigation stages. |
| `src/asx_investigator/investigation/claim_compiler.py` | Convert a validated selected hypothesis into deterministic claim text. |
| `src/asx_investigator/agent/reasoning.py` | Assertion-ID-only hypothesis and challenge contracts plus deterministic validation. |
| `src/asx_investigator/agent/gemini.py` | Prompts and schemas for the two bounded model calls. |
| `src/asx_investigator/evidence/context.py` | Bounded reasoning packet construction from assertions. |
| `src/asx_investigator/storage/memory.py` | Typed admission and retrieval of allowed shared memory entries. |
| `src/asx_investigator/storage/repository.py` | SQLite schema/migrations for ledger and shared-memory records. |
| `src/asx_investigator/evaluation/bundles.py` | External frozen case-bundle loader and generic recorded gateway. |
| `src/asx_investigator/evaluation/gold.py` | Gold execution and result aggregation without reading sealed labels at runtime. |
| `src/asx_investigator/confidence/calibration.py` | Offline calibration artifact construction and band safety checks. |
| `evals/run_gold_evals.py` | Execute external frozen cases and write PASS, FAIL or NOT_RUN reports. |
| `web/src/App.tsx` | Assertion, mechanism, ledger and calibration-status display. |

## Task 1: Define Phase 3 contracts and documentation baseline

**Files:**
- Modify: `src/asx_investigator/domain/models.py`
- Modify: `MASTER_DEVELOPMENT_PLAN.md`
- Create: `docs/phase-plans/phase-03-causal-investigation-intelligence.md`
- Modify: `README.md`
- Modify: `design requirement document v1.md`
- Test: `tests/unit/test_phase3_contracts.py`

**Interfaces:**
- Consumes: existing `EvidenceItem`, `Hypothesis`, `InvestigationReport`, `CheckpointSummary` and confidence contracts.
- Produces: `CausalMechanism`, `EvidenceAssertion`, `MechanismTest`, `LedgerEntry`, `CalibrationMetadata` and backward-compatible additions to `InvestigationReport`.
- Later tasks use the contracts without importing implementation modules.

- [ ] **Step 1: Write the failing contract tests**

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from asx_investigator.domain.models import (
    CausalMechanism,
    EvidenceAssertion,
    EvidenceRole,
)


def test_assertion_requires_case_scoped_evidence_and_exact_span_hash() -> None:
    assertion = EvidenceAssertion(
        assertion_id="A1",
        evidence_id="E1",
        case_version_id="version-1",
        exact_text="BHP raised FY26 production guidance.",
        span_hash="a" * 64,
        artifact_hash="b" * 64,
        published_at=datetime(2026, 8, 20, 8, 30, tzinfo=UTC),
        role=EvidenceRole.CAUSAL_INPUT,
        causal_eligible=True,
    )

    assert assertion.mechanism_hint == CausalMechanism.UNKNOWN


def test_assertion_rejects_non_sha256_span_hash() -> None:
    with pytest.raises(ValidationError, match="span_hash"):
        EvidenceAssertion(
            assertion_id="A1", evidence_id="E1", case_version_id="version-1",
            exact_text="BHP raised FY26 production guidance.", span_hash="bad",
            artifact_hash="b" * 64, published_at=datetime.now(UTC),
            role=EvidenceRole.CAUSAL_INPUT, causal_eligible=True,
        )
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `../../.venv/bin/python -m pytest tests/unit/test_phase3_contracts.py -v`

Expected: FAIL because the Phase 3 domain contracts do not exist.

- [ ] **Step 3: Add minimal typed contracts with backward-compatible report fields**

```python
class CausalMechanism(StrEnum):
    MECHANICAL = "MECHANICAL"
    ISSUER_EVENT = "ISSUER_EVENT"
    SECTOR_READTHROUGH = "SECTOR_READTHROUGH"
    COMMODITY_FX = "COMMODITY_FX"
    MACRO_MARKET = "MACRO_MARKET"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    UNKNOWN = "UNKNOWN"


class EvidenceAssertion(BaseModel):
    assertion_id: str = Field(pattern=r"^A[1-9][0-9]*$")
    evidence_id: str
    case_version_id: str
    exact_text: str = Field(min_length=1, max_length=1_800)
    span_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at: datetime
    role: EvidenceRole
    causal_eligible: bool
    mechanism_hint: CausalMechanism = CausalMechanism.UNKNOWN
    normalized_entities: list[str] = Field(default_factory=list)
    normalized_values: dict[str, float] = Field(default_factory=dict)
```

Add `MechanismTest`, `LedgerEntry` and `CalibrationMetadata` with stable IDs, timestamps and version fields. Add `assertions`, `mechanism_tests`, `ledger`, and `calibration_metadata` to `InvestigationReport` with empty defaults so old payloads still validate.

- [ ] **Step 4: Synchronize product documents**

Write `docs/phase-plans/phase-03-causal-investigation-intelligence.md` with the seven milestone names from the approved design. Mark only P3.0 as in progress. Update the master plan, README and product requirement document to identify Phase 2.8 as the current release candidate and Phase 3 as planned work, not implemented capability.

- [ ] **Step 5: Run contract and documentation regression tests**

Run: `../../.venv/bin/python -m pytest tests/unit/test_phase3_contracts.py tests/unit/test_phase2_contracts.py -v && ../../.venv/bin/ruff check src tests`

Expected: PASS. Existing Phase 2 report fixtures continue to parse.

- [ ] **Step 6: Commit the contract baseline**

```bash
git add src/asx_investigator/domain/models.py MASTER_DEVELOPMENT_PLAN.md README.md \
  'design requirement document v1.md' docs/phase-plans/phase-03-causal-investigation-intelligence.md \
  tests/unit/test_phase3_contracts.py
git commit -m "feat: define phase 3 investigation contracts"
```

## Task 2: Extract the investigation kernel and append-only ledger

**Files:**
- Create: `src/asx_investigator/investigation/ledger.py`
- Create: `src/asx_investigator/investigation/kernel.py`
- Modify: `src/asx_investigator/investigation/service.py`
- Modify: `src/asx_investigator/investigation/checkpoints.py`
- Modify: `src/asx_investigator/api/app.py`
- Test: `tests/unit/investigation/test_ledger.py`
- Test: `tests/integration/test_phase3_kernel_recovery.py`

**Interfaces:**
- Consumes: `InvestigationState`, `CheckpointEnvelope`, `EvidenceItem`, `MarketMove`, stage observer and Phase 3 `LedgerEntry`.
- Produces: `InvestigationKernel.run(...) -> InvestigationKernelResult` and `LedgerBuilder.append(...) -> LedgerEntry`.
- The public `InvestigationService.investigate(...)` signature remains supported and delegates to the kernel.

- [ ] **Step 1: Write failing ledger and recovery tests**

```python
async def test_kernel_records_hash_bound_append_only_ledger_entries(recorded_tools) -> None:
    report = await InvestigationService(recorded_tools).investigate(
        "BHP", "2026-08-20", mode="RECORDED"
    )

    stages = [entry.stage for entry in report.ledger]
    assert stages[:3] == [
        "resolve_instrument", "resolve_asx_session", "acquire_market_data"
    ]
    assert all(entry.input_hashes for entry in report.ledger)
    assert report.ledger[-1].status == "COMPLETED"


async def test_resume_keeps_prior_ledger_entries_and_does_not_repeat_market_provider(tmp_path) -> None:
    # Start a durable recorded run that fails after acquire_market_data, then retry it.
    # The test gateway counts provider calls.
    assert retry_gateway.calls["get_market_data"] == 1
    assert resumed_report.ledger[2].status == "RESUMED"
```

- [ ] **Step 2: Run the kernel tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/unit/investigation/test_ledger.py tests/integration/test_phase3_kernel_recovery.py -v`

Expected: FAIL because reports do not contain a complete ledger and no `InvestigationKernel` exists.

- [ ] **Step 3: Implement the ledger builder**

```python
class LedgerBuilder:
    def __init__(self, entries: list[LedgerEntry] | None = None) -> None:
        self._entries = list(entries or [])

    def append(
        self, *, stage: str, status: str, input_hashes: list[str],
        output_hashes: list[str], policy_version: str, model_configuration: dict[str, str]
    ) -> LedgerEntry:
        entry = LedgerEntry(
            sequence=len(self._entries) + 1,
            stage=stage,
            status=status,
            input_hashes=sorted(set(input_hashes)),
            output_hashes=sorted(set(output_hashes)),
            policy_version=policy_version,
            model_configuration=model_configuration,
        )
        self._entries.append(entry)
        return entry

    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)
```

`LedgerBuilder` must reject sequence rewrites and add a `RESUMED` entry before the resumed durable stage. It stores hashes and stage metadata only, never credentials or raw content.

- [ ] **Step 4: Extract the kernel without changing public behavior**

Create `InvestigationKernel` with small methods for session/market, evidence, reasoning, publication and terminal reports. Move the current orchestration from `InvestigationService` into the kernel in behavior-preserving steps. `InvestigationService` becomes a compatibility facade:

```python
class InvestigationService:
    async def investigate(self, ticker: str, trade_date: str | date, **options) -> InvestigationReport:
        return await self.kernel.run(ticker, trade_date, **options)
```

Pass the ledger builder through stage completion. Store ledger entries in durable checkpoint state and attach them to the completed report. Do not alter the provider order, timing classification, retry policy or two-call limit in this task.

- [ ] **Step 5: Run kernel, recovery and existing integration regressions**

Run: `../../.venv/bin/python -m pytest tests/unit/investigation/test_ledger.py tests/integration/test_phase3_kernel_recovery.py tests/integration/test_p28_checkpoint_recovery.py tests/integration/test_p28_restart_recovery.py tests/integration/test_recorded_investigation.py -v && ../../.venv/bin/ruff check src tests`

Expected: PASS. A resumed run has a durable ledger and completed provider calls are not repeated.

- [ ] **Step 6: Commit the kernel extraction**

```bash
git add src/asx_investigator/investigation/ledger.py src/asx_investigator/investigation/kernel.py \
  src/asx_investigator/investigation/service.py src/asx_investigator/investigation/checkpoints.py \
  src/asx_investigator/api/app.py tests/unit/investigation/test_ledger.py \
  tests/integration/test_phase3_kernel_recovery.py
git commit -m "feat: add investigation kernel and decision ledger"
```

## Task 3: Bind hypotheses and published claims to exact evidence assertions

**Files:**
- Create: `src/asx_investigator/investigation/assertions.py`
- Create: `src/asx_investigator/investigation/mechanisms.py`
- Create: `src/asx_investigator/investigation/claim_compiler.py`
- Modify: `src/asx_investigator/evidence/context.py`
- Modify: `src/asx_investigator/agent/reasoning.py`
- Modify: `src/asx_investigator/agent/gemini.py`
- Modify: `src/asx_investigator/investigation/kernel.py`
- Test: `tests/unit/investigation/test_assertions.py`
- Test: `tests/unit/investigation/test_claim_compiler.py`
- Test: `tests/integration/test_phase3_assertion_reasoning.py`

**Interfaces:**
- Consumes: frozen `EvidenceItem`, `TradingSession`, bounded evidence packet and `CausalMechanism`.
- Produces: `build_assertions(...) -> list[EvidenceAssertion]`, `run_mechanism_tests(...) -> list[MechanismTest]`, `compile_claim(...) -> Claim`, and assertion-ID-only reasoning schemas.
- Later tasks use assertions as the only causal evidence interface for model reasoning and grading.

- [ ] **Step 1: Write failing assertion, compiler and adversarial tests**

```python
def test_assertions_are_extractable_and_case_scoped() -> None:
    assertions = build_assertions(
        [issuer_evidence("E1", "BHP raised FY26 production guidance.")],
        case_version_id="v1", session=resolve_session(date(2026, 8, 20)),
    )

    assert assertions[0].evidence_id == "E1"
    assert assertions[0].exact_text == "BHP raised FY26 production guidance."
    assert assertions[0].causal_eligible is True


def test_claim_compiler_never_publishes_model_only_text() -> None:
    claim = compile_claim(
        ticker="BHP", mechanism=CausalMechanism.ISSUER_EVENT,
        assertions=[eligible_assertion("A1", "BHP raised FY26 production guidance.")],
        model_statement="A takeover offer caused the move.",
    )

    assert "takeover" not in claim.text.lower()
    assert claim.supporting_evidence_ids == ["E1"]


async def test_unknown_assertion_or_noncausal_targeted_assertion_abstains(recorded_tools) -> None:
    report = await InvestigationService(recorded_tools, invalid_assertion_reasoner).investigate(
        "BHP", "2026-08-20", mode="LIVE"
    )

    assert report.outcome == "INSUFFICIENT_EVIDENCE"
    assert all(claim.claim_type != "CAUSE" for claim in report.claims)
```

- [ ] **Step 2: Run the assertion tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/unit/investigation/test_assertions.py tests/unit/investigation/test_claim_compiler.py tests/integration/test_phase3_assertion_reasoning.py -v`

Expected: FAIL because hypotheses still reference evidence IDs directly and claim text is not compiled from assertions.

- [ ] **Step 3: Build exact assertions and deterministic mechanism tests**

```python
def build_assertions(
    evidence: list[EvidenceItem], *, case_version_id: str, session: TradingSession
) -> list[EvidenceAssertion]:
    return [
        EvidenceAssertion(
            assertion_id=f"A{index}", evidence_id=item.evidence_id,
            case_version_id=case_version_id, exact_text=item.passage[:1800],
            span_hash=sha256(item.passage.encode()).hexdigest(),
            artifact_hash=normalized_hash(item.content_hash),
            published_at=item.published_at, role=item.role,
            causal_eligible=item.role == EvidenceRole.CAUSAL_INPUT,
            mechanism_hint=classify_mechanism_hint(item),
            normalized_entities=extract_entities(item.passage),
            normalized_values=extract_numeric_values(item.passage),
        )
        for index, item in enumerate(evidence, start=1)
    ]
```

`run_mechanism_tests` must always record `MECHANICAL` from corporate actions. It may record issuer, market-context or unknown candidates only from factual inputs. It cannot infer a causal explanation from a price pattern.

- [ ] **Step 4: Replace evidence-ID reasoning with assertion-ID reasoning**

Change `HypothesisProposal` to require `supporting_assertion_ids` and `contradicting_assertion_ids`. Change `ChallengeResult` to accept only targeted assertion IDs present in the rebuilt packet. `validate_reasoning` must reject unknown, duplicate, cross-case, post-cutoff, non-causal or contradiction-only support.

The Gemini prompts must say that assertions are untrusted evidence data, only packet assertion IDs may be cited, and model prose is not publishable.

- [ ] **Step 5: Compile the final claim deterministically**

```python
def compile_claim(
    *, ticker: str, mechanism: CausalMechanism,
    assertions: list[EvidenceAssertion], model_statement: str | None = None,
) -> Claim:
    eligible = [item for item in assertions if item.causal_eligible]
    if not eligible:
        raise ClaimCompilationError("No eligible evidence assertion")
    lead = eligible[0]
    return Claim(
        claim_id="C1", claim_type=ClaimType.CAUSE,
        text=f"{lead.exact_text} This is the leading {mechanism.value.lower()} explanation for {ticker}.",
        supporting_evidence_ids=[lead.evidence_id],
    )
```

The compiler must omit `model_statement` from output, deduplicate cited evidence in stable order and fail closed if the assertion set is invalid.

- [ ] **Step 6: Run reasoning and evidence regressions**

Run: `../../.venv/bin/python -m pytest tests/unit/investigation/test_assertions.py tests/unit/investigation/test_claim_compiler.py tests/integration/test_phase3_assertion_reasoning.py tests/unit/agent/test_reasoning.py tests/integration/test_reasoning_abstention.py tests/unit/test_evidence.py -v && ../../.venv/bin/ruff check src tests`

Expected: PASS. The agent still performs at most two model calls and at most one targeted retrieval.

- [ ] **Step 7: Commit assertion-bound reasoning**

```bash
git add src/asx_investigator/investigation/assertions.py src/asx_investigator/investigation/mechanisms.py \
  src/asx_investigator/investigation/claim_compiler.py src/asx_investigator/evidence/context.py \
  src/asx_investigator/agent/reasoning.py src/asx_investigator/agent/gemini.py \
  src/asx_investigator/investigation/kernel.py tests/unit/investigation/test_assertions.py \
  tests/unit/investigation/test_claim_compiler.py tests/integration/test_phase3_assertion_reasoning.py
git commit -m "feat: compile causal claims from evidence assertions"
```

## Task 4: Enforce shared-memory admission and case isolation

**Files:**
- Create: `src/asx_investigator/storage/memory.py`
- Modify: `src/asx_investigator/storage/repository.py`
- Modify: `src/asx_investigator/investigation/kernel.py`
- Modify: `src/asx_investigator/api/app.py`
- Test: `tests/unit/storage/test_shared_memory.py`
- Test: `tests/integration/test_phase3_memory_isolation.py`

**Interfaces:**
- Consumes: SQLite database path, `SharedMemoryEntry` domain contract and case request identity.
- Produces: `SharedMemoryRepository.put_reference_fact(...)`, `list_context_facts(ticker)`, `record_provider_health(...)`, and `MemoryAdmissionPolicy.validate(...)`.
- Runtime reasoning receives only `CONTEXT_ONLY` issuer reference facts. It never receives a previous case conclusion.

- [ ] **Step 1: Write failing memory boundary tests**

```python
async def test_only_expiring_provenanced_reference_facts_are_admitted(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()
    stored = await memory.put_reference_fact(
        ticker="BHP", field="sector", value="Materials",
        source_url="https://issuer.example/profile", source_hash="a" * 64,
        valid_until=datetime(2027, 1, 1, tzinfo=UTC),
    )

    assert stored.scope == "CONTEXT_ONLY"
    assert (await memory.list_context_facts("BHP"))[0].value == "Materials"


async def test_case_claims_and_holdout_labels_cannot_enter_shared_memory(tmp_path) -> None:
    memory = SharedMemoryRepository(tmp_path / "cases.db")
    await memory.initialize()

    with pytest.raises(MemoryAdmissionError):
        await memory.put("CASE_CLAIM", {"ticker": "BHP", "claim": "Guidance caused move"})
    with pytest.raises(MemoryAdmissionError):
        await memory.put("HOLDOUT_LABEL", {"case_id": "sealed-1"})


async def test_child_refinement_does_not_receive_parent_causal_conclusion(client) -> None:
    child = await create_refinement_with_excluded_source(client)
    report = await await_completed_report(client, child.case_id)
    assert "parent causal conclusion" not in str(report["ledger"]).lower()
```

- [ ] **Step 2: Run the memory tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/unit/storage/test_shared_memory.py tests/integration/test_phase3_memory_isolation.py -v`

Expected: FAIL because no shared-memory admission policy or memory schema exists.

- [ ] **Step 3: Add the shared-memory schema and policy**

Add a `shared_memory_entries` table with `entry_id`, `memory_type`, `ticker`, `payload_json`, `source_hash`, `source_url`, `scope`, `valid_from`, `valid_until`, `policy_version`, `created_at` and `revoked_at`. Create a partial index for active entries by ticker and memory type.

```python
ALLOWED_MEMORY_TYPES = {"ISSUER_REFERENCE", "PROVIDER_HEALTH", "CALIBRATION_ARTIFACT"}


class MemoryAdmissionPolicy:
    def validate(self, memory_type: str, payload: dict[str, object]) -> None:
        if memory_type not in ALLOWED_MEMORY_TYPES:
            raise MemoryAdmissionError(f"{memory_type} is prohibited shared memory")
        if memory_type == "ISSUER_REFERENCE":
            required = {"ticker", "field", "value", "source_hash", "source_url", "valid_until"}
            if not required.issubset(payload):
                raise MemoryAdmissionError("Issuer reference facts require provenance and expiry")
```

`list_context_facts` must return only active, non-revoked issuer facts with unexpired validity and `CONTEXT_ONLY` scope. It must not return case tables, source passages, reports, claims or eval labels.

- [ ] **Step 4: Connect allowed context without making it causal evidence**

At investigation start, the kernel may load issuer reference facts for the requested ticker and write their IDs to the ledger. It may use them to select relevant market-context tools or display instrument context. It must not create `EvidenceAssertion` objects from them and must not place them in a causal support list.

- [ ] **Step 5: Run memory, refinement and API regressions**

Run: `../../.venv/bin/python -m pytest tests/unit/storage/test_shared_memory.py tests/integration/test_phase3_memory_isolation.py tests/integration/test_api_persistence.py tests/integration/test_p28_checkpoint_recovery.py -v && ../../.venv/bin/ruff check src tests`

Expected: PASS. All prohibited memory writes fail, existing case recovery works and child versions stay causally isolated.

- [ ] **Step 6: Commit memory isolation**

```bash
git add src/asx_investigator/storage/memory.py src/asx_investigator/storage/repository.py \
  src/asx_investigator/investigation/kernel.py src/asx_investigator/api/app.py \
  tests/unit/storage/test_shared_memory.py tests/integration/test_phase3_memory_isolation.py
git commit -m "feat: enforce investigation memory boundaries"
```

## Task 5: Execute frozen gold case bundles through the production path

**Files:**
- Create: `src/asx_investigator/evaluation/bundles.py`
- Modify: `src/asx_investigator/evaluation/models.py`
- Modify: `src/asx_investigator/evaluation/gold.py`
- Modify: `src/asx_investigator/evaluation/grading.py`
- Modify: `evals/run_gold_evals.py`
- Modify: `evals/gold-corpus.example.json`
- Test: `tests/unit/evaluation/test_bundles.py`
- Test: `tests/integration/test_phase3_gold_execution.py`

**Interfaces:**
- Consumes: an external gold root containing `manifest.json` and one artifact-backed bundle per case.
- Produces: `FrozenCaseBundle`, `FrozenCaseGateway`, `execute_gold_corpus(...) -> GoldExecutionReport` and `grade_report(...)` results from normal production reports.
- Sealed labels remain external and are joined only by the external grading process.

- [ ] **Step 1: Write failing bundle execution tests**

```python
async def test_gold_runner_executes_a_frozen_bundle_not_a_prebuilt_report(tmp_path) -> None:
    write_bundle(tmp_path / "gold-01", ticker="BHP", trade_date="2026-08-20")
    corpus = load_frozen_gold_corpus(tmp_path, kind="development")

    result = await execute_gold_corpus(corpus)

    assert result.status == "PASS"
    assert result.cases[0].report.market_move is not None
    assert result.cases[0].report.ledger


def test_bundle_rejects_mutated_artifact_hash(tmp_path) -> None:
    write_bundle(tmp_path / "gold-01", artifact_hash="a" * 64, artifact_bytes=b"other")

    with pytest.raises(FrozenBundleError, match="hash"):
        load_frozen_case_bundle(tmp_path / "gold-01")


async def test_missing_external_holdout_is_not_run(monkeypatch) -> None:
    monkeypatch.delenv("ASX_EVAL_HOLDOUT_ROOT", raising=False)
    result = await run_external_gold("holdout")
    assert result.status == "NOT_RUN"
```

- [ ] **Step 2: Run bundle tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/unit/evaluation/test_bundles.py tests/integration/test_phase3_gold_execution.py -v`

Expected: FAIL because the gold runner only validates manifests and grades supplied report JSON.

- [ ] **Step 3: Define the frozen bundle contract and gateway**

Each case directory contains `bundle.json` and content-addressed `artifacts/<sha256>`. The bundle declares instrument identity, daily bars, benchmark return, corporate actions, source documents, provider outcome metadata and their hashes. `FrozenCaseGateway` implements `InvestigationTools` from this bundle and returns typed provider outcomes with frozen provenance.

```python
class FrozenCaseGateway:
    def __init__(self, bundle: FrozenCaseBundle) -> None:
        self.bundle = bundle

    async def get_market_data(self, ticker: str, trade_date: date) -> MarketDataResult:
        self.bundle.assert_request(ticker, trade_date)
        return self.bundle.market_result()

    async def get_evidence(self, ticker: str, trade_date: date) -> list[EvidenceItem]:
        self.bundle.assert_request(ticker, trade_date)
        return self.bundle.evidence_items()
```

Validate every declared artifact hash before exposing data. Reject a bundle with a non-Sydney cutoff, wrong ASX session, invalid source timing, provider schema mismatch or missing required artifact.

- [ ] **Step 4: Execute and grade the same product path**

Replace report-file loading in `run_gold_evals.py` with:

```python
gateway = FrozenCaseGateway(bundle)
report = await InvestigationService(gateway, reasoner=reasoner).investigate(
    bundle.ticker, bundle.trade_date, mode="RECORDED"
)
evaluation = grade_report(manifest, report, latency_ms=elapsed_ms, estimated_cost_aud=cost_aud)
```

The development corpus may contain labels. The holdout runner writes blind report bundles and requires an external grader to supply labels. No runtime endpoint loads a holdout manifest or labels.

- [ ] **Step 5: Add deterministic gold graders for assertions and ledger integrity**

Add checks named `assertion_integrity`, `claim_compilation`, `ledger_reproducibility` and `calibration_metadata`. `assertion_integrity` requires each material claim citation to resolve through an eligible assertion with matching evidence ID and span hash. `ledger_reproducibility` executes a recorded bundle twice after volatile timestamps are normalized and compares stage, policy and artifact hashes.

- [ ] **Step 6: Run gold and existing evaluation regressions**

Run: `../../.venv/bin/python -m pytest tests/unit/evaluation/test_bundles.py tests/integration/test_phase3_gold_execution.py tests/unit/evaluation/test_harness.py tests/unit/test_p28_gold_evaluation.py -v && ../../.venv/bin/python evals/run_gold_evals.py --format markdown && ../../.venv/bin/ruff check src evals tests`

Expected: local fixture bundles PASS. Missing external development or holdout roots print `NOT_RUN` and exit zero; an invalid supplied corpus prints `FAIL` and exits non-zero.

- [ ] **Step 7: Commit production-path gold execution**

```bash
git add src/asx_investigator/evaluation/bundles.py src/asx_investigator/evaluation/models.py \
  src/asx_investigator/evaluation/gold.py src/asx_investigator/evaluation/grading.py \
  evals/run_gold_evals.py evals/gold-corpus.example.json \
  tests/unit/evaluation/test_bundles.py tests/integration/test_phase3_gold_execution.py
git commit -m "feat: execute frozen gold cases through investigation kernel"
```

## Task 6: Produce reviewed calibration artifacts and enforce release gates

**Files:**
- Create: `src/asx_investigator/confidence/calibration.py`
- Modify: `src/asx_investigator/confidence/scoring.py`
- Modify: `src/asx_investigator/evaluation/models.py`
- Modify: `src/asx_investigator/evaluation/grading.py`
- Modify: `src/asx_investigator/evaluation/gold.py`
- Test: `tests/unit/confidence/test_calibration.py`
- Test: `tests/integration/test_phase3_calibration_gate.py`

**Interfaces:**
- Consumes: completed report confidence bands, case evaluations, corpus version and confidence rule version.
- Produces: `build_calibration_artifact(...) -> CalibrationArtifact`, `CalibrationMetadata`, and release checks with raw counts, denominators and sample status.
- Calibration artifacts may enter shared product memory only through Task 4 admission policy.

- [ ] **Step 1: Write failing calibration and release-gate tests**

```python
def test_calibration_artifact_marks_small_band_samples_insufficient() -> None:
    artifact = build_calibration_artifact(
        records=[calibration_record("HIGH", correct=True)] * 4,
        corpus_version="gold-dev-v1", confidence_rule_version="confidence-v2",
    )

    assert artifact.bands["HIGH"].status == "INSUFFICIENT_SAMPLE"
    assert artifact.bands["HIGH"].eligible_cases == 4


def test_high_band_material_error_blocks_release() -> None:
    gate = evaluate_release_gates([
        calibration_record("HIGH", correct=False, material_error=True)
    ])

    assert gate.status == "FAIL"
    assert gate.raw_counts["wrong_high"] == {"passed": 0, "failed": 1}


async def test_holdout_results_do_not_change_the_active_confidence_rule(tmp_path) -> None:
    before = load_active_rule_version(tmp_path)
    await grade_external_holdout(tmp_path)
    assert load_active_rule_version(tmp_path) == before
```

- [ ] **Step 2: Run calibration tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/unit/confidence/test_calibration.py tests/integration/test_phase3_calibration_gate.py -v`

Expected: FAIL because confidence output has no empirical calibration artifact or release gate implementation.

- [ ] **Step 3: Build calibration artifacts from development results only**

```python
def build_calibration_artifact(
    records: list[CalibrationRecord], *, corpus_version: str, confidence_rule_version: str
) -> CalibrationArtifact:
    grouped = group_by_band(records)
    return CalibrationArtifact(
        corpus_version=corpus_version,
        confidence_rule_version=confidence_rule_version,
        bands={
            band: BandCalibration(
                eligible_cases=len(items),
                correct_cases=sum(item.correct for item in items),
                material_errors=sum(item.material_error for item in items),
                status="MEASURED" if len(items) >= 5 else "INSUFFICIENT_SAMPLE",
            )
            for band, items in grouped.items()
        },
    )
```

Keep the user-facing terms LOW, MEDIUM and HIGH. Do not add probability labels. Attach only the selected reviewed artifact metadata to reports. A holdout grade may compare a rule but never writes, selects or tunes it.

- [ ] **Step 4: Enforce deterministic release gates**

Implement `evaluate_release_gates` with raw count entries for `lookahead`, `session`, `citation`, `provider_semantics`, `wrong_high`, `top_1`, `top_2`, `required_abstention`, `false_abstention`, `reproducibility` and `confidence_caps`.

The safety checks fail on any error. The behavioral checks use their actual denominators and the approved thresholds: top-1 at least 75 percent, top-2 at least 90 percent, required abstention 100 percent and false abstention at most 20 percent. If no external corpus executes, return `NOT_RUN` rather than a partial pass.

- [ ] **Step 5: Run confidence and evaluation regressions**

Run: `../../.venv/bin/python -m pytest tests/unit/confidence/test_calibration.py tests/integration/test_phase3_calibration_gate.py tests/unit/test_confidence.py tests/unit/evaluation/test_harness.py -v && ../../.venv/bin/ruff check src tests`

Expected: PASS. Existing confidence caps still apply, the active rule does not mutate from evaluation, and a materially wrong HIGH result blocks release.

- [ ] **Step 6: Commit calibration and release policy**

```bash
git add src/asx_investigator/confidence/calibration.py src/asx_investigator/confidence/scoring.py \
  src/asx_investigator/evaluation/models.py src/asx_investigator/evaluation/grading.py \
  src/asx_investigator/evaluation/gold.py tests/unit/confidence/test_calibration.py \
  tests/integration/test_phase3_calibration_gate.py
git commit -m "feat: add confidence calibration release gates"
```

## Task 7: Expose causal decisions, complete release documentation and run the final gate

**Files:**
- Modify: `src/asx_investigator/api/app.py`
- Modify: `src/asx_investigator/report/markdown.py`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `README.md`
- Modify: `MASTER_DEVELOPMENT_PLAN.md`
- Modify: `docs/phase-plans/phase-03-causal-investigation-intelligence.md`
- Modify: `design requirement document v1.md`
- Create: `evals/results/phase3-evaluation.md`
- Test: `tests/integration/test_phase3_report_api.py`

**Interfaces:**
- Consumes: completed report assertions, mechanism tests, ledger and calibration metadata.
- Produces: backward-compatible JSON and Markdown report fields plus an English workbench view that does not expose chain-of-thought, raw artifacts or labels.
- Release evidence records measured commands and `PASS`, `FAIL` or `NOT_RUN` status only.

- [ ] **Step 1: Write failing API, Markdown and Workbench tests**

```python
def test_completed_report_exposes_assertions_mechanisms_ledger_and_calibration(client) -> None:
    body = completed_recorded_case(client)

    assert body["assertions"][0]["span_hash"]
    assert body["mechanism_tests"][0]["mechanism"] == "MECHANICAL"
    assert body["ledger"][-1]["status"] == "COMPLETED"
    assert "probability" not in body["calibration_metadata"]["label"].lower()
```

```tsx
it("shows causal evidence and calibration status without chain of thought", () => {
  render(<CompletedCase />)
  expect(screen.getByText("Evidence assertions")).toBeInTheDocument()
  expect(screen.getByText("Mechanism tests")).toBeInTheDocument()
  expect(screen.getByText("Calibration sample status")).toBeInTheDocument()
  expect(screen.queryByText(/chain of thought/i)).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run report and Workbench tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/integration/test_phase3_report_api.py -v && cd web && npm test -- --run`

Expected: FAIL because the report and UI do not render the new causal decision records.

- [ ] **Step 3: Render only auditable decision artifacts**

Add report sections for assertions, mechanism tests, ledger and calibration sample status. The JSON endpoint and Markdown export expose exact citations, hashes, stage metadata, rule version and count-based calibration status. They must not expose provider secrets, raw document bytes, model hidden reasoning, user-unapproved case memory or sealed labels.

In the Workbench, add compact sections titled `Evidence assertions`, `Mechanism tests`, `Decision ledger` and `Calibration sample status`. Link assertions to the existing exact passage drawer. Display `NOT_RUN` for missing external evaluation and Live gates. Keep confidence as a band without a percentage.

- [ ] **Step 4: Synchronize release documentation**

Update every Phase 3 milestone in the master plan and phase plan using actual status. Write `evals/results/phase3-evaluation.md` from fresh command output. It must list synthetic, development gold, holdout and Live results separately. If credentials or external data are absent, list the exact missing gate as `NOT_RUN`.

- [ ] **Step 5: Run the complete release sequence**

Run:

```bash
../../.venv/bin/python -m pytest -q
../../.venv/bin/ruff check .
../../.venv/bin/python evals/run_recorded_evals.py
../../.venv/bin/python evals/run_gold_evals.py --format markdown
cd web && npm test -- --run
cd web && npm run build
git diff --check
```

Expected: all local tests, lint, recorded evaluation and frontend checks pass. External development, holdout and Live gates show measured `PASS` or `FAIL`, or explicit `NOT_RUN`.

- [ ] **Step 6: Commit the release surface**

```bash
git add src/asx_investigator/api/app.py src/asx_investigator/report/markdown.py \
  web/src/App.tsx web/src/App.test.tsx README.md MASTER_DEVELOPMENT_PLAN.md \
  docs/phase-plans/phase-03-causal-investigation-intelligence.md \
  'design requirement document v1.md' evals/results/phase3-evaluation.md \
  tests/integration/test_phase3_report_api.py
git commit -m "feat: expose phase 3 causal investigation decisions"
```

## Final acceptance sequence

- [ ] Run a whole-branch review against `git merge-base main HEAD` and resolve every Critical and Important issue.
- [ ] Verify `git diff --check` and a clean worktree.
- [ ] Confirm the master plan, Phase 3 plan, README, product requirement document and evaluation result use the same release status.
- [ ] Do not label the product Live validated until the real development corpus, sealed holdout and credentialed Live smoke have all passed their respective gates.

## Self-review

**Spec coverage:** Task 1 establishes the Phase 3 public contract and documentation. Task 2 creates the single kernel and durable ledger. Task 3 binds reasoning and published claims to exact assertions. Task 4 defines the permitted memory surface and tests case isolation. Task 5 executes frozen gold bundles through the normal product path. Task 6 adds offline calibration metadata and deterministic release gates. Task 7 exposes decisions and records measured release status.

**Placeholder scan:** Every task specifies files, interfaces, failing tests, focused commands, implementation behavior and a commit. External artifacts and credentials are intentionally not invented; their absence has the explicit `NOT_RUN` outcome defined in the global constraints.

**Type consistency:** `EvidenceAssertion` is the causal input contract for reasoning, claim compilation, grading and report display. `LedgerEntry` is produced by the kernel and stored in checkpoint state. `CalibrationMetadata` is report-facing and derives only from a reviewed `CalibrationArtifact`; external holdout results cannot update it.
