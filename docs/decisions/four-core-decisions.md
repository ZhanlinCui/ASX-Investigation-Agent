# Four Core Decisions

## 1. Tools and source disagreement

The Agent does not receive an unrestricted tool belt. Deterministic planning selects from seven fixed driver lanes, and typed provider adapters perform acquisition. Every call returns one of five outcomes: `SUCCESS`, `EMPTY`, `PARTIAL`, `RETRYABLE_FAILURE` or `PERMANENT_FAILURE`. The outcome includes provider identity, retrieval time, coverage, source version, provenance and a frozen artifact reference when a response exists. This prevents a timeout or entitlement failure from being interpreted as “nothing happened.”

EODHD is the primary ASX daily-market source. Marketstack is a governed fallback when configured. A complete primary result is not blended with fallback values. If sources disagree beyond the configured tolerance, the system records both values as a material conflict, applies the field-resolution policy and caps confidence; it never averages the disagreement into a false consensus.

Discovery and causal evidence are different tools. Search can identify a promising document, but a result snippet cannot prove a cause. Issuer IR material, controlled user sources and approved original sources must be securely fetched, frozen, classified and passage-indexed before they can support an assertion. Gemini cannot call providers or expand the source taxonomy. One follow-up retrieval is allowed only when the first hypothesis response identifies a specific evidence gap within the bounded plan.

This is intentionally less flexible than an open tool-calling Agent. The trade-off is auditability: every lane, skip, failure, budget and resulting evidence ID is persisted and can be reproduced.

## 2. Context management

Source documents are long, repetitive and potentially hostile. The product stores their immutable bytes in a SHA-256 content-addressed artifact store, extracts page or block passages, and records publication time, retrieval time, authority, locator, evidence role and temporal eligibility.

Retrieval uses SQLite FTS5 plus metadata filters rather than a vector database. The final evidence packet is small and typed: deterministic market facts, exact assertions, coverage gaps, source conflicts and an allowlist of IDs the model may reference. Passage length and packet cardinality are bounded. Post-close and later material is marked retrospective context and cannot support the same trading session.

Documents, shared-memory facts and prior-model output are all untrusted data at model boundaries. The challenge call receives a sanitized ID-level representation of the first call rather than its free-form prose. Search queries, provider bodies, memory values and prompts never enter the public report. These constraints reduce recall compared with unconstrained browsing, but they make citation and timing validation enforceable.

## 3. Memory

The product separates durable audit state from reusable product context.

Each case has immutable versions, append-only events, provider calls, gaps, conflicts, reports and typed checkpoints in SQLite WAL. A refinement creates a child and preserves its parent. Checkpoints bind the request and stage artifacts; an incompatible policy cannot silently resume old state.

Cross-case shared memory is deliberately narrow. It may hold allowlisted issuer reference fields, TTL provider-health observations, source-policy versions, confidence-rule versions and reviewed calibration provenance. Every entry has provenance, validity time, expiry or revocation semantics and a content hash. It is `CONTEXT_ONLY`: it can help deterministic routing, but cannot become an evidence assertion, satisfy a mechanism test or support a claim.

Historical claims, hypotheses, model summaries, ticker conclusions and holdout labels are prohibited. Provider cache is also not “learning”; it is source-bound data with a retrieval time and TTL. The Agent therefore gets operational continuity without carrying a causal answer from one investigation into the next.

## 4. Evaluation and calibration

Evaluation is layered so that a convenient local pass cannot masquerade as real-world accuracy. Unit, property, provider-contract and adversarial tests enforce ASX sessions, timing, calculations, capture, memory isolation, prompt boundaries, citation integrity, provider-failure semantics and public-data minimization. Twenty-four recorded synthetic cases exercise stable end-to-end policy paths. They are sentinels, not historical attribution evidence.

The real development gate requires twenty-four point-in-time cases executed through the configured structured Gemini reasoner with frozen provider artifacts, evidence cutoffs, labels, abstention policy, latency and measured AUD cost. The twelve-case holdout is isolated by issuer and time, and runtime code cannot load its labels. Holdout grading cannot tune the active confidence rule.

Release metrics report raw counts and actual denominators. Top-1 and top-2 apply only to answerable explained cases; required and false abstention have separate gates. Lookahead, session errors, missing citations, unsupported claims, provider-failure misreporting and materially wrong `HIGH` explanations are zero-tolerance failures. Reproducibility compares validated decisions and artifact identities rather than harmless private-prose variation.

Confidence remains `LOW`, `MEDIUM` or `HIGH`, with visible factors and deterministic caps. Development evidence may create a reviewed ordinal calibration artifact, but no band is described as a probability. A missing corpus is `NOT_RUN`, not a pass. Stable release approval requires development, sealed holdout and credentialed Live gates to pass together.
