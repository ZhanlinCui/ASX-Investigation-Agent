# Architecture

## Design principle

The system is a controlled investigation Agent, not a general tool-calling platform. Deterministic code owns facts, time, retrieval policy, evidence identity, publication and confidence. Gemini receives a bounded evidence packet and can propose only IDs already registered by the system.

```text
API / Workbench
      |
Case manager -> immutable versions -> append-only events -> checkpoints
      |
Typed investigation kernel
      |-- market/session forensics
      |-- seven-lane retrieval plan
      |-- frozen evidence + assertion compiler
      |-- hypothesis call -> optional one-lane follow-up -> challenge call
      |-- mechanism/citation/timing validation
      |-- confidence caps + abstention
      |
Public report projection -> JSON / Markdown / UI
```

## Agent kernel

The kernel is an explicit typed state machine. It resolves the instrument and ASX session, acquires market and corporate-action facts, persists a deterministic retrieval plan, freezes evidence, builds assertions, asks for ranked hypotheses, permits at most one justified evidence-gap follow-up, challenges the leading hypothesis and validates the result before publication.

Gemini cannot call a provider, calculate a return, mint an evidence ID, change a source role, write a confidence band or publish arbitrary prose as a claim. The first structured call returns bounded hypotheses using assertion IDs. The second receives a sanitized ID-only prior decision and checks the leader for a stronger alternative, unsupported assumptions and timing leakage. Invalid schemas or model failure preserve market facts and produce an abstention.

## Retrieval lanes

Every case has the same fixed driver taxonomy:

1. issuer disclosure;
2. capital and corporate action;
3. index rebalance;
4. sector and peer;
5. commodity, FX and macro;
6. analyst event;
7. no-catalyst control.

Each lane has an entitlement rule, source policy, query/document budget and explicit `PLANNED`, `COMPLETE`, `PARTIAL`, `FAILED` or `SKIPPED` result. The persisted plan hash and safe lane summary are public; queries and provider bodies are private. Discovery identifies candidates but cannot independently support a causal claim. A source becomes causal only after secure capture, authority classification, exact passage extraction and time eligibility.

## Provider and conflict policy

Providers return `SUCCESS`, `EMPTY`, `PARTIAL`, `RETRYABLE_FAILURE` or `PERMANENT_FAILURE` with retrieval time, coverage, provenance and artifact identity. EODHD is the primary daily-market source. Marketstack is a governed fallback, not a value to average with the primary. Material OHLC or volume disagreements become conflict records and cap confidence. Required provider failures can never be translated into “no catalyst.”

Raw successful responses are stored in a SHA-256 content-addressed artifact store. The database holds safe metadata, hashes and provenance locators.

## Evidence and context

PDF, HTML and text sources are frozen before extraction. URL ingestion blocks private/reserved networks, unsafe redirects, unapproved MIME types and oversized responses. Passages retain publication and retrieval times, page/block locators, authority, temporal role and content hash. Post-close or future evidence is retrospective context, never same-session causal support.

SQLite FTS5 and metadata filters select a small packet of market facts, coverage conditions and exact assertions. Memory context is explicitly `CONTEXT_ONLY`, untrusted and non-causal. Prompts never receive raw provider responses or historical case conclusions.

## Memory architecture

Memory has four deliberately different forms:

| Scope | Content | Rule |
| --- | --- | --- |
| Run state | typed stage outputs and private model artifacts | exists only for one version and checkpoint lineage |
| Case memory | request, evidence, claims, report and append-only events | completed versions are immutable; refinements create children |
| Shared product memory | allowlisted issuer reference fields, provider health, policy/calibration versions | point-in-time, expiring/revocable, context-only |
| Cache | retrievable provider data with source, hash and TTL | performance aid, never causal memory |

Prior claims, hypotheses, model summaries, ticker conclusions and holdout labels are prohibited shared-memory categories. Shared entries cannot become assertions, pass a mechanism test or support a claim. Checkpoints bind the request and input/output artifact hashes; an incompatible policy creates an audited child version instead of resuming stale state.

## Confidence and publication

Claim support, selected-hypothesis confidence and investigation completeness are separate. Observable evidence authority, timing, market signature, coverage and conflicts enter a deterministic scoring rule. Caps prevent `HIGH` when primary support, timing resolution, disclosure coverage or required market data are inadequate. The public output remains `LOW`, `MEDIUM` or `HIGH` and is labelled `UNCALIBRATED`; it is not an empirical probability.

The claim compiler is the only route from a selected hypothesis to public causal prose. It binds assertions to their frozen evidence and constructs safe report language. The public projection is an allowlist that excludes passages, URLs, provider diagnostics, prompts, memory values and private model text. Exact passage access requires both evidence ID and case version ID.

## Recovery and audit

SQLite WAL stores cases, immutable versions, append-only run events, provider calls, conflicts, coverage gaps, checkpoints and reports. Data-producing stages write typed checkpoints. Startup and retry resume only a compatible checkpoint; otherwise the old run is terminalized and a child version records the restart. SSE uses monotonic sequence numbers for replay.

The decision ledger records stage, input/output hashes, policy version and safe validation result. It is an audit artifact, not chain-of-thought.
