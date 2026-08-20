# Task 2 Report — Freeze Live provider calls and strengthen source acquisition

## Status

Implemented and verified in the isolated `phase2/evidence-complete-live` worktree on top of Task 1 commit `7fa8813`.

## TDD evidence

### Initial RED

Command:

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_p28_live_artifacts.py \
  tests/unit/test_p28_source_egress.py \
  tests/integration/test_p28_source_provenance_api.py -v
```

Observed result before production changes:

```text
collected 14 items
12 failed, 2 passed, 1 warning in 0.38s
```

The failures were the intended missing contracts: Live adapter/store injection was absent, outcomes and diagnostics had no artifact IDs, `SourceIngestor` had no connector abstraction, production peer verification did not exist, `FrozenSource` exposed no `ArtifactReference`, and app construction created separate artifact stores.

### Initial GREEN

The same command after the minimal implementation produced:

```text
14 passed, 1 warning in 0.36s
```

### Hardening RED/GREEN cycles

Self-review added explicit tests for invalid-scheme ordering, DNS resolution failure, bounded oversized-provider metadata, and partial response capture. Before their production changes:

```text
3 failed in 0.09s
```

The failures showed invalid URLs were resolved before scheme rejection, resolver errors escaped as `OSError`, and oversized provider responses were mislabeled as `NETWORK_ERROR` without an artifact. After the focused changes:

```text
3 passed in 0.04s
```

A final response-read test first failed because a partial provider body was not frozen:

```text
1 failed in 0.09s
```

After attaching canonical partial-response metadata to the retryable failure outcome:

```text
1 passed in 0.04s
```

### Independent-review RED/GREEN cycle

The read-only security review found no Critical issues and three valid Important failure-path gaps: received empty responses had no artifact, 3xx responses could be parsed as success, and all-market-providers-failed artifacts were lost from the incomplete report. Regression tests were added before fixes:

```text
4 failed, 1 warning in 1.10s
```

After the focused fixes, the identical four-test command produced:

```text
4 passed, 1 warning in 0.27s
```

The same reviewer then inspected fix commit `78facfa` over `41e7b17` and reported:

```text
No remaining Critical or Important issues.
Ready to merge: Yes.
```

## Implementation

- Added bounded capture-before-parse for all Live JSON requests. Successful JSON is canonicalized through Task 1's `capture_provider_payload`, then parsed from stored bytes. HTTP error bodies, empty received responses, invalid JSON, redirects/non-2xx statuses, oversized responses, and partial response-read failures receive canonical metadata artifacts. Connect failures with no HTTP response retain `artifact=None`.
- Required all Live market and corporate-action adapters to receive an `ArtifactStore`, and threaded the app's store through `LiveToolGateway` into EODHD and Marketstack adapters.
- Added artifact IDs to `ProviderCallDiagnostic` construction; the existing repository path now persists those IDs. All-provider failure outcomes are carried through `DataProviderUnavailable` into incomplete-market diagnostics instead of being reduced to an error string. Recorded outcomes remain valid without artifacts.
- Reworked app construction to create one shared `ArtifactStore` for Live provider payloads and uploaded/fetched source content.
- Added `PublicAddressConnector` and a production `HttpxPublicAddressConnector`. Source ingestion validates the scheme/host, resolves and rejects the entire non-global address set immediately before each hop, disables environment proxy use in the production client, disables automatic redirects, verifies the response peer from `network_stream.server_addr`, and fails closed on absent, non-global, or mismatched peers before reading response content.
- Revalidates every absolute redirect target and permits at most three redirects. The existing 20 MB streaming cap and PDF/HTML/plain-text MIME policy remain in force. Existing PDF page and extracted-text caps were not changed.
- `FrozenSource` now owns an `ArtifactReference`; fetched references bind `locator` to the final validated URL while compatibility properties continue exposing ID/hash/MIME/size.
- Tavily results remain `DISCOVERY_ONLY`; no issuer authority is inferred from a discovery URL.
- API upload output exposes hashes/metadata without provider or uploaded raw bodies.

## Files changed

Production:

- `src/asx_investigator/providers/live.py`
- `src/asx_investigator/providers/market_adapters.py`
- `src/asx_investigator/providers/errors.py`
- `src/asx_investigator/evidence/ingestion.py`
- `src/asx_investigator/api/app.py`
- `src/asx_investigator/investigation/service.py`

Tests:

- `tests/unit/test_p28_live_artifacts.py`
- `tests/unit/test_p28_source_egress.py`
- `tests/integration/test_p28_source_provenance_api.py`
- `tests/unit/evidence/test_ingestion.py`
- `tests/unit/providers/test_market_adapters.py`
- `tests/unit/providers/test_live_discovery.py`

The brief listed `settings.py`; no change was necessary because the existing `artifact_dir` setting already provides the production store root. The fixed 20 MB and three-redirect security limits intentionally remain non-configurable constants. `investigation/service.py` was necessarily changed to surface Task 1 artifact references in diagnostics as required.

## Verification

Required focused gate:

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_p28_live_artifacts.py \
  tests/unit/test_p28_source_egress.py \
  tests/integration/test_p28_source_provenance_api.py \
  tests/integration/test_source_api.py -v
../../.venv/bin/ruff check \
  src/asx_investigator/providers \
  src/asx_investigator/evidence \
  src/asx_investigator/api
```

Observed: focused tests passed and scoped Ruff passed. Before review fixes, the expanded relevant regression produced `32 passed, 1 warning`.

Fresh full verification immediately before the report/commit:

```bash
../../.venv/bin/python -m pytest -q && \
../../.venv/bin/ruff check src tests && \
git diff --check
```

Observed:

```text
111 passed, 6 warnings in 1.67s
All checks passed!
```

`git diff --check` exited 0 with no output.

Fresh verification after resolving every Important independent-review finding:

```bash
../../.venv/bin/python -m pytest -q && \
../../.venv/bin/ruff check src tests && \
git diff --check
```

Observed:

```text
115 passed, 6 warnings in 1.69s
All checks passed!
```

`git diff --check` again exited 0 with no output.

## Self-review

- Capture ordering: provider-specific parsing only consumes the canonical artifact copy, not `response.json()`.
- Failure provenance: HTTP failures with bodies, empty received responses, invalid JSON, redirects, over-limit responses, and partial reads attach bounded canonical artifacts; a connect failure with no response does not fabricate one.
- Shared ownership: Live tools and `SourceIngestor` use the identical app-owned `ArtifactStore` object.
- Diagnostics: daily-bar and corporate-action outcomes copy their artifact IDs into report diagnostics. Both successful and all-providers-failed integration paths verify SQLite persistence.
- Egress: each redirect is resolved and validated before its connector call. Peer mismatch and absent peer are explicit rejections; non-global peers use the same fail-closed branch.
- Environment: the production HTTP client is created with `trust_env=False` and `follow_redirects=False`.
- Policy preservation: `MAX_SOURCE_BYTES` remains exactly 20 MB; MIME types remain PDF/HTML/plain text; the redirect count remains three; parsing caps are unchanged.
- Authority: discovery output remains `DISCOVERY_ONLY`; only explicit upload/fetch authority selection changes source authority.
- Compatibility: recorded provider outcomes continue to work with `artifact=None`.
- Secrets: no runtime secrets were read or printed; tests use synthetic tokens only, and frozen failure metadata excludes request URLs, query parameters, and headers.

## Concerns

- This implementation does not claim DNS pinning. It validates the full resolution set immediately before each request and then verifies the connected peer exposed by HTTPX/httpcore before reading or admitting response content. If a future transport stops exposing `network_stream.server_addr`, acquisition fails closed by design.
- The test run retains pre-existing Starlette/httpx and PyMuPDF/SWIG deprecation warnings; there are no test or lint failures.

## Follow-up Important finding fix

The formal Task 2 review identified one remaining failure-path gap: when an HTTP `Response` had been created but its `aiter_bytes()` stream failed before yielding any bytes, the adapter re-raised the read exception and returned a no-artifact `NETWORK_ERROR`, indistinguishable from a connect failure.

### TDD evidence

Added `test_zero_yield_provider_response_is_frozen_before_read_failure` beside the existing partial-read regression. The new test first failed with `artifact is None`, then passed after the focused production change. It asserts a retryable `NETWORK_ERROR`, a non-null artifact, and canonical metadata containing `body_empty`, `error_code`, and the response `status_code`.

### Fix

`request_captured_json` now captures bounded canonical zero-byte response metadata and raises `ProviderResponseReadError` with its `ArtifactReference` whenever a response stream raises an `httpx.HTTPError`, including before the first byte. Connect failures still occur before a response exists and continue through the generic network-error path with `artifact=None`. No source security limits or unrelated behavior changed.

### Focused verification

```text
../../.venv/bin/python -m pytest tests/unit/test_p28_live_artifacts.py tests/unit/providers/test_market_adapters.py -v
16 passed in 0.06s

../../.venv/bin/ruff check src/asx_investigator/providers tests/unit/test_p28_live_artifacts.py tests/unit/providers/test_market_adapters.py
All checks passed!
```

Follow-up fix commit: `c39c2fb` (`fix: preserve zero-byte provider response artifacts`).
