# P2.8 Live Readiness and Gold Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make configured Live investigations auditably reproducible through frozen provider artifacts, resumable durable checkpoints, bounded official-source retrieval, and an external gold-corpus evaluation gate.

**Architecture:** The existing SQLite WAL repository remains the system of record. Provider boundaries freeze raw responses into the content-addressed artifact store and return an immutable artifact reference with every typed outcome. The investigation state machine checkpoints only JSON-safe state whose inputs are artifact hashes, resumes from the last compatible checkpoint without replaying completed provider calls, and uses the second Gemini call to accept or reject newly frozen targeted evidence. External development and sealed-holdout manifests are parsed into the existing deterministic evaluator; missing corpus assets or credentials are explicit `NOT_RUN` results.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLite WAL via aiosqlite, httpx, PyMuPDF, React/TypeScript/Vite, pytest, ruff.

## Global Constraints

- Keep the product a single-user ASX equity investigation workbench; do not add authentication, collaboration, alerts, trading, generic agents, a vector database, PostgreSQL, object storage, queues, or automatic cross-case learning.
- All money remains AUD; all displayed timestamps remain `Australia/Sydney` with AEST/AEDT; `resolve_session` remains the ASX-session authority.
- Provider outcomes must preserve `SUCCESS`, `EMPTY`, `PARTIAL`, `RETRYABLE_FAILURE`, and `PERMANENT_FAILURE`; failure must never become a no-catalyst conclusion.
- EODHD remains the primary EOD ASX source; Marketstack may take over only when primary data fails or is missing; never average conflicting values.
- Discovery output, including Tavily, must never directly support a causal claim. Only approved official issuer material, explicitly user-supplied official material, and approved official mechanical sources may be `CAUSAL_INPUT`.
- Every Live provider fact and every admitted source document must have a content-addressed SHA-256 artifact before it enters a report. Bytes live only in the local artifact store; SQLite holds metadata and IDs.
- A case version is immutable once terminal. A retry that cannot use an unmodified compatible checkpoint must create a child version; it must not silently issue fresh calls under a sealed version.
- Gemini receives only a bounded evidence packet and makes at most two structured calls. It cannot call providers, manufacture evidence IDs, calculate market facts, or set the confidence band.
- Source ingestion accepts PDF, HTML, and plain text only; response and upload size limit is 20 MB; redirects are revalidated; environment proxy configuration is disabled; public-address validation is required for every HTTP target.
- Tests must be written and observed failing before production behavior is added. Every task ends with targeted tests, ruff, and one independent commit.
- All new product and engineering documentation is English. `NOT_RUN` is a valid, non-passing Live or holdout gate state.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `src/asx_investigator/storage/artifacts.py` | Stable artifact references and canonical JSON-byte freezing. |
| `src/asx_investigator/providers/outcomes.py` | Typed artifact reference on every provider outcome. |
| `src/asx_investigator/providers/capture.py` | Freeze live response bytes before outcome parsing. |
| `src/asx_investigator/providers/live.py` | Attach frozen acquisition artifacts to each Live provider operation. |
| `src/asx_investigator/storage/repository.py` | Schema-versioned request/report envelopes and immutable checkpoint persistence. |
| `src/asx_investigator/investigation/checkpoints.py` | Typed, JSON-safe state checkpoint contracts and compatibility checks. |
| `src/asx_investigator/investigation/service.py` | Emit/restore durable stage state and feed targeted evidence to the second model call only. |
| `src/asx_investigator/evidence/ingestion.py` | Redirect-safe, pinned-public-address source fetch policy and frozen document provenance. |
| `src/asx_investigator/agent/reasoning.py` | Challenge-time selection/rejection of one targeted frozen evidence set. |
| `src/asx_investigator/evaluation/gold.py` | External development/holdout corpus loading, structural validation, and `NOT_RUN` release results. |
| `evals/run_gold_evals.py` | Command-line gold evaluation and machine-readable release report. |
| `src/asx_investigator/api/app.py` | Checkpoint lineage and artifact metadata API fields; retry semantics. |
| `web/src/App.tsx` | Artifact provenance and checkpoint-lineage presentation without exposing raw provider bodies. |
| `tests/unit/test_p28_*.py`, `tests/integration/test_p28_*.py` | Contract, recovery, temporal, provenance, and gold-evaluation regression tests. |

### Task 1: Artifact and checkpoint contracts

**Files:**

- Create: `src/asx_investigator/providers/capture.py`
- Create: `src/asx_investigator/investigation/checkpoints.py`
- Modify: `src/asx_investigator/storage/artifacts.py`
- Modify: `src/asx_investigator/providers/outcomes.py`
- Modify: `src/asx_investigator/storage/repository.py`
- Modify: `src/asx_investigator/domain/models.py`
- Test: `tests/unit/test_p28_artifacts_checkpoints.py`

**Interfaces:**

- Consumes: `ArtifactStore.put(content: bytes, mime_type: str) -> ArtifactRecord` and `ProviderOutcome[T]`.
- Produces: `ArtifactReference`, `freeze_json_payload`, `capture_provider_payload`, `CheckpointEnvelope`, `SQLiteCaseRepository.save_checkpoint`, and `SQLiteCaseRepository.latest_compatible_checkpoint`.
- Later tasks use `ProviderOutcome.artifact`, `ProviderCallDiagnostic.artifact_id`, and checkpoint `typed_state_json` only through the types defined here.

- [ ] **Step 1: Write failing artifact and checkpoint contract tests**

```python
@pytest.mark.asyncio
async def test_provider_capture_persists_canonical_json_before_parse(tmp_path: Path):
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = capture_provider_payload(
        store, {"close": 12.34, "symbol": "BHP.AU"}, "application/json"
    )
    assert store.get(artifact.artifact_id) == b'{"close":12.34,"symbol":"BHP.AU"}'
    assert artifact.sha256 == artifact.artifact_id


@pytest.mark.asyncio
async def test_latest_checkpoint_requires_same_schema_policy_and_input_hashes(
    repository: SQLiteCaseRepository, case_version: CaseVersionRecord
):
    checkpoint = CheckpointEnvelope(
        version_id=case_version.version_id,
        stage="acquire_market_data",
        input_artifact_hashes=["a" * 64],
        output_artifact_hashes=["b" * 64],
        typed_state_json={"instrument": {"asx_code": "BHP"}},
        policy_version="phase2-v1",
    )
    await repository.save_checkpoint(checkpoint)
    assert await repository.latest_compatible_checkpoint(
        case_version.version_id, policy_version="phase2-v1", input_artifact_hashes=["a" * 64]
    ) == checkpoint
    assert await repository.latest_compatible_checkpoint(
        case_version.version_id, policy_version="phase2-v2", input_artifact_hashes=["a" * 64]
    ) is None
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `pytest tests/unit/test_p28_artifacts_checkpoints.py -v`

Expected: FAIL because the capture and checkpoint interfaces do not exist.

- [ ] **Step 3: Add immutable artifact and checkpoint types**

```python
class ArtifactReference(BaseModel):
    artifact_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str
    size_bytes: int = Field(ge=0)
    locator: str | None = None


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def capture_provider_payload(store: ArtifactStore, payload: object, mime_type: str) -> ArtifactReference:
    record = store.put(canonical_json_bytes(payload), mime_type)
    return ArtifactReference.model_validate(record.model_dump())


class CheckpointEnvelope(BaseModel):
    version_id: str
    stage: str
    input_artifact_hashes: list[str]
    output_artifact_hashes: list[str]
    typed_state_json: dict[str, object]
    schema_version: str = "checkpoint-v1"
    policy_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Add an `artifact: ArtifactReference | None = None` field to `ProviderOutcome`, retain a nullable `artifact_id` database column for legacy rows, and make the repository write a `checkpoints` table keyed by `(version_id, stage, created_at)`. Add `request_schema_version` and `report_schema_version` columns using `PRAGMA table_info` plus idempotent `ALTER TABLE` migration. Existing JSON remains readable as schema version `"phase2-v1"`; new rows are serialized with a versioned envelope:

```python
{"schema_version": "case-payload-v1", "payload": request_or_report}
```

`latest_compatible_checkpoint` must reject a checkpoint if the caller’s policy version or normalized sorted input hash list differs. It returns the most recent matching envelope or `None`.

- [ ] **Step 4: Run focused tests and lint**

Run: `pytest tests/unit/test_p28_artifacts_checkpoints.py tests/unit/test_phase2_contracts.py -v && ruff check src/asx_investigator/storage src/asx_investigator/providers src/asx_investigator/investigation`

Expected: all selected tests PASS and ruff exits 0.

- [ ] **Step 5: Commit the independently usable contracts**

```bash
git add src/asx_investigator/storage/artifacts.py src/asx_investigator/providers/capture.py src/asx_investigator/providers/outcomes.py src/asx_investigator/investigation/checkpoints.py src/asx_investigator/storage/repository.py src/asx_investigator/domain/models.py tests/unit/test_p28_artifacts_checkpoints.py
git commit -m "feat: add live artifact and checkpoint contracts"
```

### Task 2: Freeze Live provider calls and strengthen source acquisition

**Files:**

- Modify: `src/asx_investigator/providers/live.py`
- Modify: `src/asx_investigator/providers/market_adapters.py`
- Modify: `src/asx_investigator/evidence/ingestion.py`
- Modify: `src/asx_investigator/api/app.py`
- Modify: `src/asx_investigator/settings.py`
- Test: `tests/unit/test_p28_live_artifacts.py`
- Test: `tests/unit/test_p28_source_egress.py`
- Test: `tests/integration/test_p28_source_provenance_api.py`

**Interfaces:**

- Consumes: `ArtifactReference` and `capture_provider_payload` from Task 1; `SourceIngestor.fetch` endpoint contract.
- Produces: all Live `ProviderOutcome` instances carry an artifact reference, and `FrozenSource` exposes an artifact reference with the final validated URL.
- Later tasks treat artifact IDs as checkpoint inputs and only retrieve targeted evidence through frozen `EvidenceItem` objects.

- [ ] **Step 1: Write failing tests for Live capture and egress**

```python
@pytest.mark.asyncio
async def test_eodhd_success_has_raw_response_artifact(respx_mock, live_tools, artifacts):
    respx_mock.get("https://eodhd.com/api/eod/BHP.AU").respond(
        200, json=[{"date": "2025-01-02", "close": 42.0}]
    )
    outcome = await live_tools.get_corporate_actions("BHP", date(2025, 1, 2))
    assert outcome.artifact is not None
    assert artifacts.get(outcome.artifact.artifact_id)


@pytest.mark.asyncio
async def test_redirect_target_is_resolved_and_revalidated(ingestor, public_resolver, http_client):
    http_client.route("https://public.example/start").respond(302, headers={"location": "http://127.0.0.1/x"})
    with pytest.raises(SourceRejected, match="Private and reserved"):
        await ingestor.fetch("https://public.example/start")


@pytest.mark.asyncio
async def test_source_api_returns_hash_but_never_provider_raw_body(client):
    response = await client.post("/api/v1/sources/upload", files={"file": ("notice.txt", b"Official notice", "text/plain")})
    body = response.json()
    assert body["artifact_id"].isalnum()
    assert "Official notice" not in body.values()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_p28_live_artifacts.py tests/unit/test_p28_source_egress.py tests/integration/test_p28_source_provenance_api.py -v`

Expected: FAIL because Live tools do not capture raw provider payloads and source provenance lacks the hardened policy.

- [ ] **Step 3: Implement capture-before-parse and deterministic source policy**

For every HTTP response in `LiveInvestigationTools`, read bounded bytes once, validate the HTTP status, pass JSON payloads to `capture_provider_payload`, then parse the captured payload. Attach its reference to the returned `ProviderOutcome`; capture non-success response metadata as canonical JSON as well, unless no response bytes exist (for example a connect timeout). Thread the `ArtifactStore` from app construction into Live tool construction. Record `outcome.artifact.artifact_id` in `record_provider_call` and surface the ID in `ProviderCallDiagnostic`.

Add an injected `PublicAddressConnector` protocol around the concrete transport:

```python
class PublicAddressConnector(Protocol):
    async def get(self, url: httpx.URL, allowed_addresses: set[str]) -> httpx.Response: ...
```

The production connector must: resolve the host immediately before each request; reject non-global results; disable `trust_env`; reject the response if its peer address is absent or not in the prevalidated set; use `follow_redirects=False`; and cause `SourceRejected` rather than returning bytes when address validation fails. The test connector may expose a peer address explicitly. Revalidate the absolute redirect URL on every hop, cap redirects at three, cap stream bytes at `MAX_SOURCE_BYTES`, and retain PDF extraction page/text caps already used by parsing. Do not infer `PRIMARY_ISSUER` from a search-result domain; preserve `DISCOVERY_ONLY` until explicitly uploaded/fetched with an approved authority selection.

- [ ] **Step 4: Run focused tests and full ingestion regression**

Run: `pytest tests/unit/test_p28_live_artifacts.py tests/unit/test_p28_source_egress.py tests/integration/test_p28_source_provenance_api.py tests/integration/test_source_api.py -v && ruff check src/asx_investigator/providers src/asx_investigator/evidence src/asx_investigator/api`

Expected: all selected tests PASS and ruff exits 0.

- [ ] **Step 5: Commit the isolated Live acquisition gate**

```bash
git add src/asx_investigator/providers/live.py src/asx_investigator/providers/market_adapters.py src/asx_investigator/evidence/ingestion.py src/asx_investigator/api/app.py src/asx_investigator/settings.py tests/unit/test_p28_live_artifacts.py tests/unit/test_p28_source_egress.py tests/integration/test_p28_source_provenance_api.py
git commit -m "feat: freeze live provider and source acquisitions"
```

### Task 3: Resume from durable checkpoints without replaying providers

**Files:**

- Modify: `src/asx_investigator/investigation/service.py`
- Modify: `src/asx_investigator/api/app.py`
- Modify: `src/asx_investigator/storage/repository.py`
- Modify: `src/asx_investigator/investigation/checkpoints.py`
- Test: `tests/integration/test_p28_checkpoint_recovery.py`
- Test: `tests/integration/test_p28_restart_recovery.py`

**Interfaces:**

- Consumes: `CheckpointEnvelope`, `save_checkpoint`, and `latest_compatible_checkpoint` from Task 1, plus artifact-bearing provider diagnostics from Task 2.
- Produces: `InvestigationService.investigate(..., resume_checkpoint: CheckpointEnvelope | None = None)` and a stage observer payload with `checkpoint` ready for repository persistence.
- Later tasks may rely on reports exposing the terminal checkpoint chain and artifact hashes.

- [ ] **Step 1: Write failing recovery tests using counting tools**

```python
@pytest.mark.asyncio
async def test_resume_after_market_checkpoint_does_not_repeat_market_calls(app, counting_tools):
    version_id = await start_and_interrupt(app, after_stage="acquire_market_data")
    before = counting_tools.market_calls
    await app.state.case_manager.retry(version_id)
    assert counting_tools.market_calls == before
    events = await app.state.repository.list_events(version_id)
    assert any(event.status == "RESUMED" and event.stage == "acquire_market_data" for event in events)


@pytest.mark.asyncio
async def test_incompatible_checkpoint_creates_child_retry(app, repository):
    version_id = await start_and_interrupt(app, after_stage="discover_and_freeze_documents")
    await repository.invalidate_checkpoint_policy(version_id, "phase2-v2")
    child = await app.state.case_manager.retry(version_id)
    assert child.parent_version_id == version_id
    assert child.version_id != version_id
```

- [ ] **Step 2: Run recovery tests to verify they fail**

Run: `pytest tests/integration/test_p28_checkpoint_recovery.py tests/integration/test_p28_restart_recovery.py -v`

Expected: FAIL because retries re-run from `resolve_instrument` and no durable stage payload exists.

- [ ] **Step 3: Make the state machine checkpointable at each durable boundary**

Introduce an `InvestigationState` Pydantic model in `checkpoints.py` with JSON-safe optional fields for `instrument`, `session`, `market_data`, `corporate_actions`, `evidence`, `coverage_gaps`, `conflicts`, `packet`, `hypothesis_batch`, and `challenge`. Do not store an open HTTP response, tool instance, model client, or arbitrary Python exception in it.

At the completion of each stage that has produced data, call the observer with:

```python
{
    "checkpoint": CheckpointEnvelope(
        version_id=version_id,
        stage=stage,
        input_artifact_hashes=state.input_hashes(),
        output_artifact_hashes=state.output_hashes(),
        typed_state_json=state.model_dump(mode="json"),
        policy_version="phase2-v1",
    ).model_dump(mode="json")
}
```

Restore only completed state from the latest compatible checkpoint, emit a `RESUMED` run event, and skip the completed provider stage. A checkpoint taken before a stage is never sufficient to skip that stage. `CaseManager.retry` must either continue the nonterminal version from a valid checkpoint or create a new child version with `parent_version_id` and an event explaining the incompatible checkpoint. Startup recovery uses the same decision path. A completed version remains immutable.

- [ ] **Step 4: Run recovery, persistence, and API tests**

Run: `pytest tests/integration/test_p28_checkpoint_recovery.py tests/integration/test_p28_restart_recovery.py tests/integration/test_api_persistence.py tests/integration/test_api.py -v && ruff check src/asx_investigator/investigation src/asx_investigator/storage src/asx_investigator/api`

Expected: all selected tests PASS and ruff exits 0.

- [ ] **Step 5: Commit recovery behavior**

```bash
git add src/asx_investigator/investigation/service.py src/asx_investigator/investigation/checkpoints.py src/asx_investigator/storage/repository.py src/asx_investigator/api/app.py tests/integration/test_p28_checkpoint_recovery.py tests/integration/test_p28_restart_recovery.py
git commit -m "feat: resume investigations from durable checkpoints"
```

### Task 4: Admit targeted evidence only through the second structured challenge

**Files:**

- Modify: `src/asx_investigator/agent/reasoning.py`
- Modify: `src/asx_investigator/agent/gemini.py`
- Modify: `src/asx_investigator/investigation/service.py`
- Modify: `src/asx_investigator/evidence/context.py`
- Test: `tests/unit/test_p28_targeted_reasoning.py`
- Test: `tests/integration/test_p28_targeted_retrieval.py`

**Interfaces:**

- Consumes: frozen evidence IDs, centralized evidence-policy filtering, and Task 2’s document artifacts.
- Produces: `ChallengeResult.accepted_targeted_evidence_ids`, a validated selected hypothesis based only on initial or targeted frozen evidence, and no more than two model calls.
- Later tasks use report validation results and diagnostics; they must not call the model again.

- [ ] **Step 1: Write failing test for a model gap resolved by frozen targeted evidence**

```python
@pytest.mark.asyncio
async def test_second_call_can_select_only_frozen_targeted_evidence(recorded_tools, reasoner):
    reasoner.generate_result = HypothesisBatch(
        hypotheses=[proposal("H1", ["E1"])],
        evidence_gap=EvidenceGapRequest(purpose="Need the issuer release", query="BHP production guidance"),
    )
    reasoner.challenge_result = ChallengeResult(
        leading_hypothesis_id="H1",
        stronger_alternative_id=None,
        timing_leakage=False,
        unsupported_assumptions=[],
        summary="The targeted issuer release confirms the supplied announcement.",
        accepted_targeted_evidence_ids=["T1"],
    )
    report = await InvestigationService(recorded_tools, reasoner).investigate("BHP", "2025-01-02")
    assert "T1" in report.validation_results[-1].evidence_ids
    assert reasoner.call_count == 2


@pytest.mark.asyncio
async def test_excluded_or_post_cutoff_target_is_not_visible_to_challenge(recorded_tools, reasoner):
    report = await InvestigationService(recorded_tools, reasoner).investigate(
        "BHP", "2025-01-02", excluded_evidence_ids=["T1"], evidence_cutoff=datetime(2025, 1, 2, 16, tzinfo=SYDNEY)
    )
    assert report.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert "T1" not in reasoner.challenge_packet.allowed_evidence_ids
```

- [ ] **Step 2: Run targeted-reasoning tests to verify they fail**

Run: `pytest tests/unit/test_p28_targeted_reasoning.py tests/integration/test_p28_targeted_retrieval.py -v`

Expected: FAIL because the challenge schema cannot select targeted IDs and `_reason` generates a batch before targeted evidence is eligible.

- [ ] **Step 3: Extend only the challenge contract, not the model-call budget**

Add this bounded field to `ChallengeResult`:

```python
accepted_targeted_evidence_ids: list[str] = Field(default_factory=list, max_length=12)
```

After the first call requests one evidence gap, retrieve once, freeze the returned document artifacts, classify timing, deduplicate, and apply the *same* `primary_only`, `excluded_evidence_ids`, and `evidence_cutoff` policy used by the initial acquisition. Rebuild the evidence packet with candidates. The second `challenge` call receives the original ranked batch plus that packet and may accept or reject eligible targeted IDs. It may not add a hypothesis, change ranks, or cite a target outside `packet.allowed_evidence_ids`.

`validate_reasoning` must reject unknown accepted targeted IDs, selected supporting IDs that are not causal input, timing leakage, and challenge unsupported assumptions. The published hypothesis/claim text remains reconstructable from exact cited passages. If no selected hypothesis remains valid after the challenge, return `INSUFFICIENT_EVIDENCE`; never manufacture a no-catalyst conclusion from a filtered child scope.

- [ ] **Step 4: Run reasoning and recorded integration regressions**

Run: `pytest tests/unit/test_p28_targeted_reasoning.py tests/integration/test_p28_targeted_retrieval.py tests/integration/test_reasoning_abstention.py tests/integration/test_recorded_investigation.py -v && ruff check src/asx_investigator/agent src/asx_investigator/investigation src/asx_investigator/evidence`

Expected: all selected tests PASS and ruff exits 0.

- [ ] **Step 5: Commit bounded targeted retrieval**

```bash
git add src/asx_investigator/agent/reasoning.py src/asx_investigator/agent/gemini.py src/asx_investigator/investigation/service.py src/asx_investigator/evidence/context.py tests/unit/test_p28_targeted_reasoning.py tests/integration/test_p28_targeted_retrieval.py
git commit -m "feat: validate targeted evidence in challenge call"
```

### Task 5: Load external gold corpora and report release gates honestly

**Files:**

- Create: `src/asx_investigator/evaluation/gold.py`
- Create: `evals/run_gold_evals.py`
- Modify: `src/asx_investigator/evaluation/models.py`
- Modify: `src/asx_investigator/evaluation/manifests.py`
- Modify: `src/asx_investigator/evaluation/grading.py`
- Modify: `evals/run_recorded_evals.py`
- Create: `tests/unit/test_p28_gold_evaluation.py`
- Create: `tests/integration/test_p28_gold_eval_cli.py`
- Create: `evals/gold-corpus.example.json`

**Interfaces:**

- Consumes: report evidence IDs and artifact hashes, ASX session resolver, evaluation case contracts, and `ASX_EVAL_DEVELOPMENT_ROOT` / `ASX_EVAL_HOLDOUT_ROOT` environment variables.
- Produces: `GoldCorpusLoadResult`, `GoldReleaseReport`, `load_gold_corpus`, `run_gold_evals`, and a JSON/Markdown report that distinguishes `PASS`, `FAIL`, and `NOT_RUN`.
- Task 6 displays only the summary/provenance, never sealed labels.

- [ ] **Step 1: Write failing external-corpus tests**

```python
def test_absent_external_holdout_is_not_run(monkeypatch):
    monkeypatch.delenv("ASX_EVAL_HOLDOUT_ROOT", raising=False)
    result = load_gold_corpus("holdout")
    assert result.status == "NOT_RUN"
    assert result.cases == []


def test_gold_manifest_rejects_future_evidence_and_wrong_session(tmp_path: Path):
    write_manifest(tmp_path, cases=[gold_case(evidence_cutoff="2025-01-02T16:10:00+11:00", future_evidence_ids=["E9"])])
    result = load_gold_corpus("development", root=tmp_path)
    assert result.status == "FAIL"
    assert "future_evidence_ids" in result.errors[0]


def test_release_report_has_raw_counts_proportions_and_case_failures():
    report = grade_gold_cases([passing_case(), failing_case()])
    assert report.raw_counts["lookahead"] == {"passed": 1, "failed": 1}
    assert report.proportions["lookahead"] == 0.5
    assert report.case_failures[0].case_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_p28_gold_evaluation.py tests/integration/test_p28_gold_eval_cli.py -v`

Expected: FAIL because no external gold-corpus loader or release report exists.

- [ ] **Step 3: Add strict manifest validation and non-deceptive release results**

Define an external `manifest.json` contract with `schema_version: "gold-eval-v1"`, exactly `24` cases for development and exactly `12` for holdout when a corpus is supplied. Each case must contain `case_id`, `ticker`, `trade_date`, `timezone`, `evidence_cutoff`, `artifact_ids`, `future_evidence_ids`, `driver_labels`, `acceptable_alternatives`, `mechanical_expectation`, `coverage_expectation`, `citation_requirements`, and `abstention_allowed`. Assert the timezone is `Australia/Sydney`, the date is an ASX trading day, all IDs are SHA-256 values where applicable, and future evidence IDs are disjoint from eligible evidence IDs.

Use `ASX_EVAL_DEVELOPMENT_ROOT` for development and `ASX_EVAL_HOLDOUT_ROOT` for holdout. Neither external location nor labels are committed. The committed example must contain an empty `cases` array and explanatory field names only. Missing roots return a report with `status: "NOT_RUN"`, `reason`, zero evaluated cases, and never a passing gate.

Run each case through the normal recorded investigation path constructed from its frozen artifact fixture. Grade temporal integrity, ASX session, numerical market facts, citations, top-1/top-2 driver/alternative acceptance, abstention, mechanical expectation, coverage/provider-failure semantics, latency and cost. Produce raw passed/failed counts, denominator-safe proportions, and one failure record per failed case. The LLM judge field is diagnostic-only and cannot change `status`.

- [ ] **Step 4: Run gold and existing evaluator tests**

Run: `pytest tests/unit/test_p28_gold_evaluation.py tests/integration/test_p28_gold_eval_cli.py tests/unit/test_phase2_contracts.py -v && python evals/run_gold_evals.py --format json && ruff check src/asx_investigator/evaluation evals`

Expected: selected tests PASS; CLI prints a JSON `NOT_RUN` report when external roots are absent; ruff exits 0.

- [ ] **Step 5: Commit external evaluation plumbing**

```bash
git add src/asx_investigator/evaluation/gold.py src/asx_investigator/evaluation/models.py src/asx_investigator/evaluation/manifests.py src/asx_investigator/evaluation/grading.py evals/run_gold_evals.py evals/run_recorded_evals.py evals/gold-corpus.example.json tests/unit/test_p28_gold_evaluation.py tests/integration/test_p28_gold_eval_cli.py
git commit -m "feat: add external gold evaluation release reporting"
```

### Task 6: Expose provenance and close the P2.8 gates

**Files:**

- Modify: `src/asx_investigator/domain/models.py`
- Modify: `src/asx_investigator/storage/repository.py`
- Modify: `src/asx_investigator/api/app.py`
- Modify: `web/src/App.tsx`
- Modify: `web/src/App.test.tsx`
- Modify: `README.md`
- Modify: `MASTER_DEVELOPMENT_PLAN.md`
- Modify: `docs/phase-plans/phase-02-evidence-complete-live-investigation.md`
- Create: `evals/results/p2-8-live-readiness.md`
- Test: `tests/integration/test_p28_provenance_api.py`

**Interfaces:**

- Consumes: artifact-bearing provider diagnostics, `CheckpointEnvelope` chain, and `GoldReleaseReport` from Tasks 1–5.
- Produces: backward-compatible report/API fields `artifact_hashes` and `checkpoint_lineage`; Workbench visibility for artifact ID, retrieval time, source version, stage, and resume lineage.
- Release status is based solely on actual command output and may remain `NOT_RUN` for missing credentials or external assets.

- [ ] **Step 1: Write failing API and Workbench provenance tests**

```python
@pytest.mark.asyncio
async def test_report_exposes_checkpoint_lineage_and_provider_artifacts(client):
    case = await create_completed_case(client)
    body = (await client.get(f"/api/v1/investigations/{case['case_id']}")).json()
    assert body["report"]["checkpoint_lineage"][-1]["stage"] == "confidence_and_abstention"
    assert body["report"]["provider_diagnostics"][0]["artifact_id"]
    assert "artifact_content" not in body["report"]["provider_diagnostics"][0]
```

```tsx
it("shows evidence provenance without rendering a probability", () => {
  render(<App />)
  expect(screen.getByText(/Artifact SHA-256/i)).toBeInTheDocument()
  expect(screen.queryByText(/confidence probability/i)).not.toBeInTheDocument()
})
```

- [ ] **Step 2: Run provenance tests to verify they fail**

Run: `pytest tests/integration/test_p28_provenance_api.py -v && cd web && npm test -- --run`

Expected: FAIL because report payloads do not contain checkpoint lineage and the Workbench does not render it.

- [ ] **Step 3: Implement backward-compatible provenance rendering and documentation**

Add `checkpoint_lineage: list[CheckpointSummary]` to `InvestigationReport` with an empty default. Build it from repository checkpoint metadata (`stage`, `created_at`, `input_artifact_hashes`, `output_artifact_hashes`, `schema_version`, `policy_version`) but never return raw artifact bytes from case-report endpoints. Preserve the already version-scoped exact-evidence endpoint for explicitly requested passage content.

Add a compact Workbench `Provenance` section: provider, operation, retrieval timestamp, source version, artifact SHA-256, and a checkpoint-stage list. Keep the confidence display as `LOW`, `MEDIUM`, or `HIGH` plus factors/caps; no percentage or probability labels. Ensure incomplete/`NOT_RUN` statuses use explicit copy.

Update documentation to mark P2.8 features as implemented only after their test commands pass. Record the actual current Live and gold status in `evals/results/p2-8-live-readiness.md`; if credentials or external assets are absent, use `NOT_RUN` and list the missing gate, not a fabricated result.

- [ ] **Step 4: Run production-equivalent verification**

Run: `pytest -q && ruff check . && python evals/run_recorded_evals.py && python evals/run_gold_evals.py --format markdown && cd web && npm test -- --run && npm run build`

Expected: Python tests, ruff, recorded evaluation, frontend tests, and production build pass. Gold and credentialed Live results are either measured PASS/FAIL or explicit `NOT_RUN`.

- [ ] **Step 5: Commit the release-facing surface**

```bash
git add src/asx_investigator/domain/models.py src/asx_investigator/storage/repository.py src/asx_investigator/api/app.py web/src/App.tsx web/src/App.test.tsx README.md MASTER_DEVELOPMENT_PLAN.md docs/phase-plans/phase-02-evidence-complete-live-investigation.md evals/results/p2-8-live-readiness.md tests/integration/test_p28_provenance_api.py
git commit -m "feat: expose p2.8 investigation provenance"
```

## Final Acceptance Sequence

- [ ] Run `git diff --check` and verify the branch has no uncommitted work.
- [ ] Run `pytest -q`, `ruff check .`, `python evals/run_recorded_evals.py`, `python evals/run_gold_evals.py --format markdown`, `cd web && npm test -- --run`, and `cd web && npm run build`.
- [ ] If provider credentials are available only through environment variables, run the Live smoke command and record its actual output. Do not print, commit, or browser-expose credentials.
- [ ] Run a whole-branch code review against `git merge-base main HEAD`, resolve all Critical and Important findings, and rerun affected tests.
- [ ] Update `evals/results/p2-8-live-readiness.md` with command evidence and all `PASS` / `FAIL` / `NOT_RUN` release statuses.

## Self-Review

**Spec coverage:** Task 1 implements artifact/checkpoint contracts and schema envelopes. Task 2 freezes all provider/document inputs and hardens fetch policy. Task 3 turns stage state into recoverable immutable checkpoints. Task 4 fixes the targeted-evidence/model-call sequencing without creating a third model call. Task 5 implements external 24/12 corpus ingestion, strict point-in-time checks, raw metrics, and honest `NOT_RUN` reporting. Task 6 exposes provenance, documents actual gate results, and runs the release verification suite. The deferred production-platform features are excluded by Global Constraints.

**Placeholder scan:** This plan intentionally contains no unresolved implementation markers or deferred task instructions; every task has exact paths, test names, command expectations, and commit messages.

**Type consistency:** `ArtifactReference` is the sole artifact contract used by `ProviderOutcome`, `ProviderCallDiagnostic`, and source artifacts. `CheckpointEnvelope` owns checkpoint serialization and is passed between repository, stage observer, and service. `GoldReleaseReport` is generated only by the gold evaluation loader/grader and only read by Task 6 documentation/reporting.
