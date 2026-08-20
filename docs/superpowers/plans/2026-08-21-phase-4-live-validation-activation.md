# Phase 4 Live Validation Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure the existing ASX Investigation Agent against real point-in-time data and make a release decision without widening product scope.

**Architecture:** Phase 3 already supplies one typed investigation kernel, frozen bundles, the sealed-holdout boundary, deterministic graders and safe public reports. Phase 4 activates these paths with external inputs and completes model-usage accounting; it does not add a second agent, data path, memory store or confidence scheme.

**Tech Stack:** Python 3.12, FastAPI, SQLite/WAL, Pydantic, Gemini structured reasoning, approved provider adapters, frozen SHA-256 artifacts, pytest, pnpm/Vite.

## Global Constraints

- All money is AUD; public timestamps use `Australia/Sydney` AEST/AEDT and sessions use the ASX cash-market calendar.
- Secrets remain environment-only and never enter commits, artifacts, public reports or logs.
- Runtime receives no sealed-holdout labels. Only an external grader may read them.
- Missing credentials, corpora, model usage or pricing evidence are `NOT_RUN` or `FAIL`, never a pass.
- Keep two structured Gemini calls, one bounded retrieval, case isolation and ordinal `LOW`/`MEDIUM`/`HIGH` confidence.
- Add no vendors, vector search, user accounts, alerts, trading, or cross-case conclusion learning.

---

## File Structure

- `src/asx_investigator/agent/gemini.py` — structured Gemini calls and private usage capture.
- `src/asx_investigator/evaluation/models.py` — immutable model-usage and AUD-pricing contracts.
- `src/asx_investigator/evaluation/gold.py` — frozen production-path execution and external-gate outcomes.
- `evals/run_gold_evals.py` — environment-gated external evaluation entry point.
- `tests/unit/agent/test_gemini.py` — Gemini response/usage contract tests.
- `tests/integration/test_phase3_gold_execution.py` — production-path execution and measured-cost tests.
- `evals/results/phase4-live-validation.md` — immutable aggregate release record, created only after a real run.

### Task 1: Capture hash-bound Gemini usage and derived AUD cost

**Status:** Implemented and verified locally; external pricing values remain runtime configuration.

**Files:**
- Modify: `src/asx_investigator/agent/gemini.py`
- Modify: `src/asx_investigator/evaluation/models.py`
- Modify: `src/asx_investigator/settings.py`
- Test: `tests/unit/agent/test_gemini.py`

**Interfaces:**
- Consumes: Gemini `usage_metadata`, `Settings.gemini_model`, and a versioned AUD pricing schedule.
- Produces: `ModelUsageCostArtifact.recorded(...)` values through `GeminiInvestigationReasoner.consume_model_usage_cost_artifacts()`.

- [x] **Step 1: Write failing response-usage tests**

```python
def test_gemini_reasoner_records_hash_bound_usage_cost_after_structured_call(fake_client):
    reasoner = GeminiInvestigationReasoner(
        Settings(gemini_pricing_schedule_version="gemini-aud-v1"), client=fake_client
    )
    asyncio.run(reasoner.generate(packet()))
    [artifact] = reasoner.consume_model_usage_cost_artifacts()
    assert artifact.input_tokens == 100
    assert artifact.output_tokens == 20
    assert artifact.measured_cost_aud > 0
    assert artifact.artifact_hash


def test_gemini_reasoner_rejects_missing_usage_or_pricing(fake_client):
    reasoner = GeminiInvestigationReasoner(Settings(), client=fake_client)
    asyncio.run(reasoner.generate(packet()))
    assert reasoner.consume_model_usage_cost_artifacts() == []
```

- [x] **Step 2: Run the focused tests to verify RED**

Run: `../../.venv/bin/python -m pytest tests/unit/agent/test_gemini.py -v`

Expected: FAIL because the production reasoner currently does not expose observed usage-cost artifacts.

- [x] **Step 3: Implement the minimum immutable accounting boundary**

```python
def consume_model_usage_cost_artifacts(self) -> list[ModelUsageCostArtifact]:
    artifacts, self._usage_cost_artifacts = self._usage_cost_artifacts, []
    return artifacts


def _record_usage(self, usage_metadata: object) -> None:
    tokens = parse_gemini_usage(usage_metadata)
    if tokens is None or self._pricing_schedule is None:
        return
    self._usage_cost_artifacts.append(
        ModelUsageCostArtifact.recorded(
            model_configuration=self.model_configuration,
            pricing_schedule_version=self._pricing_schedule.version,
            input_tokens=tokens.input_tokens,
            output_tokens=tokens.output_tokens,
            measured_cost_aud=float(self._pricing_schedule.cost_for(**tokens.model_dump())),
        )
    )
```

Define `AudPricingSchedule` in `evaluation/models.py` with version, input/output AUD-per-million-token rates and a canonical hash. Read it from non-secret environment configuration. Missing, malformed, zero-cost or mismatched data yields no artifact; the evaluator already returns `NOT_RUN`.

- [x] **Step 4: Run focused tests to verify GREEN**

Run: `../../.venv/bin/python -m pytest tests/unit/agent/test_gemini.py -v`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/asx_investigator/agent/gemini.py src/asx_investigator/evaluation/models.py src/asx_investigator/settings.py tests/unit/agent/test_gemini.py
git commit -m "feat: capture Gemini evaluation usage cost"
```

### Task 2: Prove external development evaluation uses observed model cost

**Status:** Implemented and verified locally; no development corpus is available to execute.

**Files:**
- Modify: `src/asx_investigator/evaluation/gold.py`
- Modify: `evals/run_gold_evals.py`
- Test: `tests/integration/test_phase3_gold_execution.py`

**Interfaces:**
- Consumes: a 24-case frozen development corpus, `GeminiInvestigationReasoner` and its drained `ModelUsageCostArtifact` values.
- Produces: existing `GoldExecutionReport` case costs and artifact hashes; caller-supplied cost estimates remain unsupported.

- [x] **Step 1: Write failing execution tests**

```python
def test_external_execution_is_not_run_without_observed_reasoner_cost(frozen_development):
    result = asyncio.run(execute_gold_corpus(frozen_development, reasoner=NoUsageReasoner()))
    assert result.status == "NOT_RUN"
    assert "immutable recorded model usage" in result.reason


def test_external_execution_records_both_replay_cost_artifacts(frozen_development, usage_reasoner):
    result = asyncio.run(execute_gold_corpus(frozen_development, reasoner=usage_reasoner))
    assert result.cases[0].estimated_cost_aud > 0
    assert len(result.cases[0].cost_artifact_hashes) == 4
```

- [x] **Step 2: Run the focused tests to verify RED**

Run: `../../.venv/bin/python -m pytest tests/integration/test_phase3_gold_execution.py -v`

Expected: FAIL until the real reasoner produces the same immutable artifact contract as fixtures.

- [x] **Step 3: Retain the fail-closed runner and remove estimate pathways**

```python
first_cost = _consume_measured_case_cost(reasoner, model_configuration)
if first_cost is None:
    return _cost_not_run(corpus, model_configuration)
```

Keep `evals/run_gold_evals.py` argument-free for cost: it must instantiate the configured reasoner and derive measured values only from post-call artifacts. It exits non-zero only for supplied invalid/failing corpora; absent roots remain `NOT_RUN` with exit zero.

- [x] **Step 4: Run focused tests to verify GREEN**

Run: `../../.venv/bin/python -m pytest tests/integration/test_phase3_gold_execution.py -v`

Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/asx_investigator/evaluation/gold.py evals/run_gold_evals.py tests/integration/test_phase3_gold_execution.py
git commit -m "feat: require observed external evaluation cost"
```

### Task 3: Execute externally supplied validation without releasing labels

**Files:**
- Modify: `evals/run_gold_evals.py`
- Create: `evals/results/phase4-live-validation.md`
- Modify: `MASTER_DEVELOPMENT_PLAN.md`
- Modify: `README.md`
- Test: `tests/integration/test_p28_gold_eval_cli.py`

**Interfaces:**
- Consumes: `ASX_EVAL_DEVELOPMENT_ROOT`, `ASX_EVAL_HOLDOUT_ROOT`, approved runtime credentials, and the label-free frozen-bundle/external-grader boundary.
- Produces: `GoldExecutionReport` for development and blind holdout runtime reports; the release record contains only aggregate external-grader metrics.

- [ ] **Step 1: Write failing release-record tests**

```python
def test_release_record_is_aggregate_only(external_release_report):
    payload = external_release_report.model_dump(mode="json")
    assert "driver_labels" not in json.dumps(payload)
    assert payload["denominators"]["top_1_attribution"] > 0


def test_cli_absent_roots_is_explicit_not_run():
    completed = subprocess.run([sys.executable, "evals/run_gold_evals.py"], capture_output=True)
    assert completed.returncode == 0
    assert b"NOT_RUN" in completed.stdout
```

- [ ] **Step 2: Run focused tests to verify RED**

Run: `../../.venv/bin/python -m pytest tests/integration/test_p28_gold_eval_cli.py -v`

Expected: FAIL until the external-grader aggregate record is integrated without exposing labels.

- [ ] **Step 3: Record only measured aggregate results**

```python
def public_release_summary(result: ReleaseGateReport) -> dict[str, object]:
    return {
        "status": result.status,
        "raw_counts": result.raw_counts,
        "denominators": result.denominators,
        "proportions": result.proportions,
        "failures": result.failures,
    }
```

Do not change public documents to `release-approved` unless development, sealed holdout and Live smoke have each supplied measured results and all hard gates pass. Otherwise record the exact `OPEN`, `FAIL` or `NOT_RUN` status.

- [ ] **Step 4: Run external validation**

Run: `../../.venv/bin/python evals/run_gold_evals.py --format markdown`

Expected: development executes 24 cases with measured latency/AUD cost; holdout produces blind reports for the external grader; absent inputs remain `NOT_RUN`.

- [ ] **Step 5: Commit**

```bash
git add evals/run_gold_evals.py evals/results/phase4-live-validation.md MASTER_DEVELOPMENT_PLAN.md README.md tests/integration/test_p28_gold_eval_cli.py
git commit -m "docs: record phase 4 validation decision"
```

## Self-Review

- **Spec coverage:** Tasks 1–3 cover the remaining code prerequisite (real model usage/cost), external corpus execution, sealed-holdout isolation, provider/live inputs and truthful release records.
- **Placeholder scan:** The only unavailable elements are named external credentials and corpora; every code boundary, type and command is concrete.
- **Type consistency:** Existing `ModelUsageCostArtifact`, `GoldExecutionReport` and `ReleaseGateReport` stay authoritative. Task 1 introduces `AudPricingSchedule` and its hash; no duplicate evaluation-report types are created.

## Execution Handoff

Implement Tasks 1–2 immediately. Task 3 remains blocked until the listed external inputs are supplied; execute it with the existing subagent-driven workflow, then independently review each release record.
