# Product

## Positioning

**Evidence-first investigation for unusual ASX equity moves.**

ASX Investigation Agent accepts an ASX ticker and trading date, reconstructs the observed move and investigates why it happened. The result is a confidence-rated explanation whose material claims cite frozen, time-eligible evidence.

The intended users are professional analysts reviewing an unexplained move, technical evaluators assessing a controlled Agent architecture and product reviewers who need to challenge the result rather than trust a narrative.

## User problem

Unusual price moves rarely have one clean input. The issuer may publish before open or after close; corporate actions can explain mechanical gaps; a sector, index, commodity or analyst event may matter; two price providers can disagree; and older articles can be mistaken for contemporaneous news. A useful product must establish source timing and coverage before it explains causality.

## Product workflow

1. Resolve the ASX instrument and historically correct trading session.
2. Acquire price, volume, benchmark and corporate-action facts through typed providers.
3. Execute seven bounded retrieval lanes with explicit budgets and failure states.
4. Freeze approved sources and extract exact passages.
5. Build a compact packet of market facts, assertions, gaps and conflicts.
6. Ask Gemini for ranked hypotheses and, separately, a challenge to the leader.
7. Validate timing, mechanisms, citations and evidence identities in deterministic code.
8. Apply confidence caps or abstain, persist the version and publish public audit artifacts.

## What users receive

- AUD close-to-close, opening-gap, intraday, turnover and benchmark-relative facts;
- a leading explanation and ranked alternatives;
- supporting and contradicting evidence IDs;
- exact frozen passages available through a version-scoped viewer;
- lane-by-lane retrieval coverage, skipped reasons and failures;
- source conflicts and coverage gaps;
- confidence band, completeness, factors and deterministic caps;
- immutable version history, recovery trace and Markdown export.

## Outcomes

The lifecycle (`QUEUED`, `RUNNING`, `COMPLETED`, `FAILED_RECOVERABLE`, `FAILED`) is separate from the investigation outcome:

- `EXPLAINED` — a causal claim passed evidence, timing and publication validation;
- `NO_IDENTIFIABLE_CATALYST` — required retrieval completed and found no eligible cause;
- `INSUFFICIENT_EVIDENCE` — a plausible explanation could not meet the evidence contract;
- `INCOMPLETE_DATA` — a required provider, session or historical source was unavailable.

## Explicit limits

The product does not predict prices, recommend investments or execute trades. It is single-user software for local or controlled review, without authentication or multi-tenancy. Discovery breadth is bounded and can miss a legitimate catalyst; safe abstention is therefore part of the product rather than an error state.

External development gold, sealed holdout and credentialed Live approval are not bundled with the repository and currently remain `NOT_RUN`. The release candidate is not described as calibrated or production-validated.
