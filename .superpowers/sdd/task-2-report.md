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

## Implementation

- Added bounded capture-before-parse for all Live JSON requests. Successful JSON is canonicalized through Task 1's `capture_provider_payload`, then parsed from stored bytes. HTTP error bodies, invalid JSON, oversized responses, and partial response-read failures receive canonical metadata artifacts. Connect failures with no response bytes retain `artifact=None`.
- Required all Live market and corporate-action adapters to receive an `ArtifactStore`, and threaded the app's store through `LiveToolGateway` into EODHD and Marketstack adapters.
- Added artifact IDs to `ProviderCallDiagnostic` construction; the existing repository path now persists those IDs. Recorded outcomes remain valid without artifacts.
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

Observed: focused tests passed and scoped Ruff passed. The expanded relevant regression produced `32 passed, 1 warning`.

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

## Self-review

- Capture ordering: provider-specific parsing only consumes the canonical artifact copy, not `response.json()`.
- Failure provenance: HTTP failures with bodies, invalid JSON, over-limit responses, and partial reads attach bounded canonical artifacts; a connect failure with no response does not fabricate one.
- Shared ownership: Live tools and `SourceIngestor` use the identical app-owned `ArtifactStore` object.
- Diagnostics: both daily-bar outcomes and corporate-action outcomes copy their artifact IDs into report diagnostics, and the API integration test verifies SQLite persistence.
- Egress: each redirect is resolved and validated before its connector call. Peer mismatch and absent peer are explicit rejections; non-global peers use the same fail-closed branch.
- Environment: the production HTTP client is created with `trust_env=False` and `follow_redirects=False`.
- Policy preservation: `MAX_SOURCE_BYTES` remains exactly 20 MB; MIME types remain PDF/HTML/plain text; the redirect count remains three; parsing caps are unchanged.
- Authority: discovery output remains `DISCOVERY_ONLY`; only explicit upload/fetch authority selection changes source authority.
- Compatibility: recorded provider outcomes continue to work with `artifact=None`.
- Secrets: no runtime secrets were read or printed; tests use synthetic tokens only, and frozen failure metadata excludes request URLs, query parameters, and headers.

## Concerns

- This implementation does not claim DNS pinning. It validates the full resolution set immediately before each request and then verifies the connected peer exposed by HTTPX/httpcore before reading or admitting response content. If a future transport stops exposing `network_stream.server_addr`, acquisition fails closed by design.
- The test run retains pre-existing Starlette/httpx and PyMuPDF/SWIG deprecation warnings; there are no test or lint failures.
