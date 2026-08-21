# Evaluation

## Objective

Evaluation answers two different questions: does the product obey its safety contract, and does it correctly attribute previously unseen market moves? A large local test count can answer the first. It cannot substitute for the second.

## Evaluation layers

| Layer | Purpose | Repository state |
| --- | --- | --- |
| Domain and property tests | ASX sessions, AEST/AEDT, returns, corporate actions, citations and confidence caps | Included and run in CI |
| Provider contracts | Empty, partial, timeout, rate limit, schema drift, capture and source conflict behavior | Included and run in CI |
| Adversarial tests | Lookahead, recycled news, ticker ambiguity, prompt injection, duplicate IDs, memory leakage and public-surface exposure | Included and run in CI |
| Recorded policy sentinels | Stable end-to-end workflow and release invariants on synthetic frozen fixtures | 24 cases included; currently passing |
| Development gold | Real point-in-time attribution, abstention, latency and measured AUD model cost | 24 external cases; `NOT_RUN` |
| Sealed holdout | Issuer/time-isolated blind generalization and ordinal confidence review | 12 externally controlled cases; `NOT_RUN` |
| Credentialed Live | Completed-session provider behavior and end-to-end evidence acquisition | External credentials/canaries; `NOT_RUN` |

The recorded 24-case suite is not historical accuracy evidence. It is a compact set of policy sentinels designed to make regressions reproducible.

## Frozen case contract

An external case binds market bars, benchmark facts, corporate actions, source documents, provider outcomes, retrieval cutoff, policy versions and artifact hashes. Every artifact is SHA-256 verified before the Agent runs. Each bar must be an ASX trading day and every causal source must be eligible at the evidence cutoff.

Runtime code can execute blind holdout inputs but cannot load holdout labels. Labels and grading are supplied through the separately controlled holdout root. Serialized reports, driver labels or grading payloads inside model-visible evidence are rejected.

Gold execution uses the configured structured reasoner, not the deterministic recorded fallback. Paid evaluation fails closed before a model call unless a validated AUD pricing schedule is present. Token usage, including thinking tokens, is captured in immutable cost artifacts and recomputed with `Decimal` arithmetic.

## Labels and metrics

Each labelled case defines the leading driver, acceptable alternatives, expected outcome, future-evidence blacklist, required citations, coverage expectation and typed abstention policy: `REQUIRED`, `ALLOWED` or `FORBIDDEN`.

- Top-1 and top-2 attribution are measured only on answerable, published `EXPLAINED` cases.
- Required abstention is measured separately and must have a non-zero denominator.
- False abstention measures answerable cases the product declined to explain.
- Grounding requires all material claims to resolve to eligible evidence.
- Temporal integrity rejects post-cutoff causal support.
- Replay compares validated decisions, evidence/assertion identities, coverage and policy trace, not harmless variation in private model prose.
- Latency and measured AUD cost are reported per case with model, policy and pricing versions.

## Hard release gates

The following must be zero:

- lookahead violations;
- incorrect ASX-session attribution;
- missing material citations;
- materially unsupported published claims;
- provider failures reported as no catalyst;
- materially wrong `HIGH` explanations.

Additional thresholds for the external development and holdout sets are top-1 at least 75%, top-2 at least 90%, required abstention 100% and false abstention no more than 20%. Every percentage must include raw passed/failed counts and the actual denominator. A required metric with no eligible observations fails rather than passing vacuously.

## Calibration

Confidence is currently an ordinal evidence-strength band. Development data may produce a content-addressed calibration artifact with per-band counts and proportions. It becomes report metadata only after explicit review. Holdout results cannot write or tune the active confidence rule. Until the external protocol is complete, every report remains `UNCALIBRATED` and no probability interpretation is permitted.

## Running available evaluations

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests evals
.venv/bin/python evals/run_recorded_evals.py
.venv/bin/python evals/run_gold_evals.py --format markdown
```

Missing external roots return `NOT_RUN`. A supplied malformed or incomplete corpus returns `FAIL`. Neither state can approve a stable release. See [Release status](release-status.md) and the machine-oriented [final release record](../evals/results/final-release.md).
