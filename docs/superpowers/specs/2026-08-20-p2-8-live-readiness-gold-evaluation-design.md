# P2.8 Live Readiness and Gold Evaluation

## Decision

P2.8 prepares the existing investigation product for trustworthy configured Live use. It does not begin a general platform phase. The work is limited to live source truth, recoverable execution, and point-in-time evaluation.

The recommended approach is to finish all three together. A Live smoke run without frozen source artifacts cannot be audited. A real evaluation suite without the same production acquisition path cannot prove the product is safe. Exact stage recovery matters because repeating a live run can retrieve changed pages or changed provider data under the same case version.

Two alternatives were considered and rejected:

- Run a credentialed smoke test first, then build the evaluation corpus later. This would demonstrate connectivity but not trustworthy output.
- Move directly to production infrastructure such as authentication, PostgreSQL, and multi-user access. This would make an unproven investigation process easier to operate.

## Product Boundary

The product remains a single-user ASX equity investigation workbench. Input is an ASX code and an ASX trading date. Output is a cited explanation or an explicit abstention. All money is AUD. All user-facing times use AEST or AEDT. The ASX calendar remains the authority for sessions.

P2.8 does not add trade recommendations, alerts, monitoring, collaboration, mobile authoring, a plugin system, generic agents, or automatic cross-case learning.

## Workstream A: Live Source Truth

Every live provider call must produce a frozen acquisition record before it can affect a report. The record contains the request identity, retrieval time, provider and source version, response bytes or canonical payload, SHA-256 hash, MIME type, and an artifact locator. The database stores metadata and hashes; the artifact store owns bytes.

The provider gateway returns a typed outcome as it does today. P2.8 extends each outcome with an artifact reference. Provider failures remain distinct from successful empty responses. EODHD stays primary for daily ASX prices. Marketstack remains a fallback and comparison source. Values are never averaged.

Official issuer material is the preferred causal source. Discovery results may propose a retrieval target but cannot by themselves support a causal claim. The target retrieval step must freeze any admitted document, run its passages through the same timing and FTS rules, and allow the second structured model call to select or reject the new evidence.

URL ingestion moves behind controlled network egress. The fetcher must validate every redirect target, disable environment proxies, enforce size and MIME limits, and connect only to an approved resolved public address. PDF ingestion must retain page and extracted-text limits.

## Workstream B: Recoverable Investigation Runs

Each durable stage stores an immutable checkpoint envelope:

```text
version_id
stage
input_artifact_hashes
output_artifact_hashes
typed_state_json
schema_version
created_at
```

The state machine may resume only from a checkpoint whose input artifacts and policy versions remain valid. A retry never overwrites a sealed case version. If a stage has no valid checkpoint, the system creates a child retry version or records a clear terminal failure. It does not silently issue new live calls under an old version.

The report trace points to the final event sequence and to the checkpoint chain used to produce it. This makes the displayed report reproducible from stored inputs.

## Workstream C: Gold Point-in-Time Evaluation

The development corpus contains 24 real cases. The sealed holdout contains 12 cases. Issuers and time windows are separated between the two sets. Gold labels remain outside the repository for the sealed set.

Each case records:

- ASX code, session date, timezone, and evidence cutoff.
- Frozen market and evidence artifacts, including every rejected or future document.
- Leading driver label, acceptable alternatives, and whether abstention is allowed.
- Mechanical-action expectation and coverage expectation.
- Exact citation requirements and a short adjudication note.

Evaluation runs the same investigation path used by configured Live cases against frozen artifacts. It reports raw counts and per-case failures for session attribution, numeric facts, source timing, citation grounding, driver ranking, abstention, provider-failure semantics, latency, and cost. A model judge may describe failures but cannot pass a release gate.

Confidence remains a LOW, MEDIUM, or HIGH evidence-strength band. P2.8 does not add probability language. Calibration is deferred until the real corpus is large enough for an independent calibration split.

## Release Gates

P2.8 is complete only when all of the following are true:

1. A configured Live smoke suite completes against EODHD, Marketstack where available, Tavily where enabled, and Gemini without exposing credentials to the browser or repository.
2. Every provider-derived fact and admitted document in a Live report resolves to an immutable artifact hash.
3. A forced interruption after each durable stage resumes without repeating an already checkpointed provider call under the same version.
4. The 24-case development corpus and the external 12-case holdout run with zero lookahead, session, citation, and unsupported-material-claim violations.
5. Evaluation results contain raw counts, proportions, and a case-level failure record. Missing credentials or holdout assets produce `NOT_RUN`, never a pass.
6. The workbench exposes source provenance, artifact hashes, checkpoint lineage, coverage gaps, and conflicts without presenting an ordinal confidence score as a probability.

## Acceptance Tests

- Provider contract tests cover success, empty, partial, rate limit, timeout, schema drift, conflict, and artifact persistence.
- Security tests cover private targets, redirect chains, DNS changes, MIME deception, oversized response bodies, and oversized PDF extraction.
- Recovery tests interrupt at every stage, restart the application, and prove which stage resumed and which provider calls were not repeated.
- Recorded integration tests reproduce report claims, evidence IDs, hashes, and trace references after normalizing only volatile identifiers and retrieval times.
- Live smoke tests are skipped with an explicit `NOT_RUN` result when credentials are absent.
- Gold evaluation tests enforce cutoff time, ASX session, mechanical expectation, citation grounding, top-1/top-2 ranking, abstention, and provider-failure semantics.

## Deferred Work

PostgreSQL, object storage, queues, authentication, multi-user access, deployment telemetry, and probability calibration stay out of P2.8. They belong to the next production-readiness decision after the Live and gold-evaluation gates pass.
