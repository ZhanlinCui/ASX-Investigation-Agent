# EODHD Live Smoke Design

**Status:** Approved by default autonomy; implementation follows the existing Phase 4 activation plan.

## Goal

Provide one bounded, credentialed smoke gate for the existing EODHD ASX adapters. It must demonstrate that an ASX equity can be resolved, that a daily OHLCV slice is acquired under the primary-source policy, and that the ASX corporate-actions entitlement returns an auditable typed outcome.

## Scope

- Add an environment-gated CLI and typed report for one ticker and one completed ASX session.
- Reuse `LiveToolGateway`, `EODHDProvider`, `EODHDCorporateActionsProvider`, `ArtifactStore` and `ProviderOutcome` unchanged as the ownership boundaries.
- Save content-addressed provider snapshots below ignored `data/`; publish only safe provider status, coverage, metadata and artifact hashes.
- Keep the command offline-safe: missing `EODHD_API_KEY` returns `NOT_RUN`; invalid credentials, entitlement failures, rate limits, schema failures and incomplete market coverage return named `FAIL` results.

## Non-goals

- No new data vendor, discovery source, model call, causal narrative, confidence update, portfolio feature or automatic live release approval.
- No hard-coded key, token argument or browser-visible configuration.
- No use of EODHD corporate-action effective dates as a substitute for an announcement timestamp.

## Data contract

EODHD remains the daily ASX market-data primary through `GET /api/eod/{CODE}.AU`. The smoke gate requests only daily JSON bars for a bounded historical window. Corporate actions use `GET /api/asx-corporate-actions` with the same `.AU` ticker and a single target date. The latter is beta, refreshes daily and may be unavailable to plans without the entitlement; this condition is reported rather than hidden. EODHD documentation confirms the EOD endpoint parameters and the ASX action endpoint's entitlement, pagination and daily-refresh constraints.

## Execution semantics

```text
validate completed ASX session
-> resolve CODE as ASX instrument
-> acquire/reconcile primary daily bars
-> fetch corporate-actions outcome
-> freeze provider responses
-> render safe JSON or Markdown smoke report
```

`PASS` requires a resolved ASX instrument, a `SUCCESS` primary EOD outcome containing the requested session, a frozen artifact for each successful provider response, and a successful or genuine empty corporate-action outcome. `NOT_RUN` is limited to absent credentials. Any configured-provider failure is `FAIL` with a safe error code; it cannot become “no catalyst.”

## Verification

- Unit tests cover missing credential, non-trading date, market provider failure, corporate-action entitlement failure, artifact references and safe report projection.
- A real execution is opt-in via `EODHD_API_KEY` and records the actual output in the Phase 4 release evidence only after review.
- The existing recorded suite stays network-free.
