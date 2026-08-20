# Task 1 — Artifact and checkpoint contracts

## Scope delivered

- Added immutable `ArtifactReference` and deterministic provider payload capture.
- Exported `canonical_json_bytes` and compatibility alias `freeze_json_payload`.
- Added the optional `ProviderOutcome.artifact` reference.
- Added immutable `CheckpointEnvelope`, SQLite persistence, and compatibility lookup.
- Added idempotent SQLite migration support for checkpoint storage, legacy case-payload schema columns, and nullable legacy `provider_calls.artifact_id`.
- Preserved legacy request/report JSON reads as schema version `phase2-v1`; writes use the `case-payload-v1` envelope.

`ProviderCallDiagnostic.artifact_id` already existed in the public domain model, so it was retained unchanged for backward compatibility.

## RED evidence

1. `pytest tests/unit/test_p28_artifacts_checkpoints.py -v`
   - Failed at collection with `ModuleNotFoundError: No module named 'asx_investigator.investigation.checkpoints'` before the new contracts existed.
2. After adding the initial contracts, the same command failed `test_capture_types_are_immutable_and_alias_the_canonical_serializer` because assignment to `ArtifactReference.mime_type` did not raise.
3. After freezing the models, the same command failed `test_case_payloads_are_versioned_and_legacy_payloads_remain_readable` because a pre-existing legacy `provider_calls` table had no `artifact_id` migration.

## GREEN evidence

Fresh verification command:

```text
pytest tests/unit/test_p28_artifacts_checkpoints.py tests/unit/test_phase2_contracts.py tests/unit/storage -v
```

Result: `16 passed in 0.11s`.

```text
ruff check src/asx_investigator/storage src/asx_investigator/providers src/asx_investigator/investigation
```

Result: `All checks passed!`

`git diff --check` also exited cleanly.

## Self-review

- Artifact identifiers and checksums are constrained to lowercase SHA-256 digests in the new artifact contract.
- Checkpoint matching filters by schema and policy then compares sorted input-hash lists, preserving the original stored envelope when returned.
- Checkpoint table key is `(version_id, stage, created_at)`.
- Migrations use `PRAGMA table_info` followed by conditional `ALTER TABLE`, and the migration test invokes `initialize()` twice.
- Existing request/report public payloads remain unwrapped when read; only newly persisted values are wrapped.
- No provider adapters, UI files, or credentials were accessed or changed.

## Non-blocking test-environment concern

`pytest tests/unit -q` cannot collect the repository’s entire unit suite because pre-existing imports fail: `tests/unit/agent/test_gemini.py` imports `tests.unit.agent.test_reasoning`, but `tests.unit` is not importable in this test configuration. With `PYTHONPATH=.`, that import remains unresolved. The focused Task 1, phase-2 contract, and storage suites above are green.

## Reviewer fix — terminal checkpoint immutability

`SQLiteCaseRepository.save_checkpoint` now loads the case version before inserting and raises `CaseVersionImmutableError` when its status is `COMPLETED` or `FAILED` (the existing `TERMINAL_STATUSES` set). Added `test_completed_version_rejects_checkpoint_save`, which completes a version and verifies checkpoint persistence is rejected.

Exact verification command and output:

```text
pytest tests/unit/test_p28_artifacts_checkpoints.py tests/unit/test_phase2_contracts.py tests/unit/storage -v && ruff check src/asx_investigator/storage src/asx_investigator/providers src/asx_investigator/investigation
17 passed in 0.11s
All checks passed!
```
