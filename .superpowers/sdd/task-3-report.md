# Task 3 Report — Resume from durable checkpoints without provider replay

## Status

Implemented in the isolated `phase2/evidence-complete-live` worktree on top of
`3b593c9`. Recovery now restores only state covered by a completed durable
boundary, and retry and startup use the same compatibility/branching path.

## Scope delivered

- Added JSON-safe `InvestigationState` and `MarketDataCheckpoint` Pydantic
  models. Durable state contains only domain values, provider outcomes,
  evidence, packets, reasoning structures, hashes, and trace data; it never
  stores clients, tools, HTTP responses, exceptions, or tasks.
- Threaded the repository-owned `version_id`, the canonical normalized-request
  checksum, source artifact hashes, and an optional `CheckpointEnvelope` into
  `InvestigationService.investigate` without changing existing callers.
- Persisted checkpoints after completed data-producing stages from instrument
  resolution through deterministic validation. The observer supplies the full
  envelope to `CaseManager`; the repository persists it before the completion
  event. Public events retain checkpoint metadata and hashes but strip private
  `typed_state_json`.
- Frozen output artifact hashes per stage. Later checkpoint inputs combine the
  sealed request/source inputs with preceding frozen stage outputs. Targeted
  retrieval outputs exclude evidence already frozen by document discovery.
- Made the completed stage authoritative. Checkpoint validation rejects fields
  or frozen output stages beyond the declared boundary, and service replay
  decisions use `has_completed(stage)` rather than optional-field presence.
- Retry accepts the existing case ID and the task-required version ID. A valid
  checkpoint resumes the same `FAILED_RECOVERABLE` version and emits `RESUMED`.
  Missing, malformed, policy-mismatched, request-mismatched, artifact-mismatched,
  or state-mismatched checkpoints create a child version.
- Added an atomic repository operation that retires an incompatible current
  parent, creates and selects its queued child, and writes both
  `CHECKPOINT_INCOMPATIBLE` events in one `BEGIN IMMEDIATE` transaction.
- Startup invokes the identical recovery/branching path and considers only the
  current nonterminal version for each case, so superseded recoverable ancestors
  cannot displace a newer completed version.
- Preserved completed-version immutability and existing create/refinement/API
  behavior.

## TDD evidence

### Clean baseline

The project virtualenv was required; a raw system `pytest -q` could not collect
three pre-existing package-style imports. The correct project command was:

```text
../../.venv/bin/python -m pytest -q
116 passed, 6 warnings in 1.69s
```

### Initial RED

Tests were written before Task 3 production changes using a complete counting
gateway and deterministic one-shot provider interruption; no arbitrary sleeps
were used.

```text
../../.venv/bin/python -m pytest \
  tests/integration/test_p28_checkpoint_recovery.py \
  tests/integration/test_p28_restart_recovery.py -v

6 failed in 0.58s
```

The failures were the intended missing behavior: no durable market checkpoint,
retry accepted only case IDs and replayed the whole pipeline, startup replayed
instrument/market/benchmark calls, and checkpointless startup reused the parent.

### Initial GREEN

```text
../../.venv/bin/python -m pytest \
  tests/integration/test_p28_checkpoint_recovery.py \
  tests/integration/test_p28_restart_recovery.py -v

6 passed in 0.84s
```

### Hardening RED/GREEN cycles

- Malformed checkpoint JSON: failed with an escaping `JSONDecodeError`, then
  passed after candidate deserialization became an incompatible-child result.
- Public event state: failed because `typed_state_json` appeared in checkpoint
  events, then passed after persistence stripped typed state from the event copy.
- Superseded restart: failed because a historical recoverable ancestor replaced
  the completed current version, then passed after current-version filtering.
- Completed-stage authority: failed because a session checkpoint containing
  future market state resumed the parent without a market call, then passed
  after future-field rejection and boundary-authoritative skip decisions.
- Targeted lineage: failed because new targeted evidence appeared in both input
  and output hashes, then passed after per-stage output hashes were frozen.
- Direct service inputs: failed because changed current inputs were ignored, then
  passed after service-level comparison against checkpoint initial inputs.
- Atomic branching: failed with missing
  `create_checkpoint_recovery_child`, then passed after the single-transaction
  parent/child/event implementation.

The expanded recovery/restart suite finished with `12 passed in 1.01s` before
the final required and full gates.

## Review record

The first read-only review returned **Not ready** with one Critical and four
Important findings: future-stage field trust, mutable targeted lineage, missing
direct-service input comparison, non-atomic incompatible branching, and narrow
early-stage/no-artifact test coverage. Every Critical/Important finding received
a focused regression and implementation fix. Coverage now includes an
artifact-bearing interruption after document discovery and verifies that
instrument, market, benchmark, corporate-action, and evidence providers are not
replayed. A bounded follow-up review was requested on the repaired tree but did
not return within the review window and was interrupted rather than delaying the
required handoff indefinitely.

## Final verification

Required Task 3 gate, run fresh immediately before commit:

```text
../../.venv/bin/python -m pytest \
  tests/integration/test_p28_checkpoint_recovery.py \
  tests/integration/test_p28_restart_recovery.py \
  tests/integration/test_api_persistence.py \
  tests/integration/test_api.py -v && \
../../.venv/bin/ruff check \
  src/asx_investigator/investigation \
  src/asx_investigator/storage \
  src/asx_investigator/api

21 passed, 1 warning in 1.84s
All checks passed!
```

Fresh full regression and lint gate:

```text
../../.venv/bin/python -m pytest -q && \
../../.venv/bin/ruff check src tests && \
git diff --check

128 passed, 6 warnings in 2.53s
All checks passed!
```

`git diff --check` exited 0 with no output.

## Concerns

- The suite still reports the repository's pre-existing Starlette/httpx and
  PyMuPDF/SWIG deprecation warnings; there are no test or lint failures.
- Recovery compatibility is intentionally policy-versioned. A future change to
  provider/reasoning semantics must bump `CHECKPOINT_POLICY_VERSION` so older
  checkpoints branch rather than resume under changed rules.

No credentials were read or added, and no UI files were changed.
