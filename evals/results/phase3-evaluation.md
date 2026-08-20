# Phase 3 Evaluation Record

Recorded on 21 August 2026 from the Phase 3 release worktree. This record distinguishes executable local checks from external gates. `NOT_RUN` is not a pass.

## Local code and workbench

| Check | Status | Result |
|---|---|---|
| `../../.venv/bin/python -m pytest -q` | PASS | 272 passed; 6 third-party deprecation warnings |
| `../../.venv/bin/ruff check src tests evals` | PASS | All checks passed |
| `git diff --check` | PASS | No whitespace errors |
| `cd web && pnpm test -- --run` | PASS | 5 tests passed |
| `cd web && pnpm build` | PASS | TypeScript and Vite production build passed |

## Local synthetic and recorded evaluation

| Check | Status | Result |
|---|---|---|
| `../../.venv/bin/python evals/run_recorded_evals.py` | PASS | 24 of 24 synthetic policy sentinels passed; 0 failed |

These cases test orchestration and safety behavior. They are not historical attribution accuracy evidence.

## External development gold corpus

| Check | Status | Result |
|---|---|---|
| `../../.venv/bin/python evals/run_gold_evals.py --format markdown --estimated-case-cost-aud 0.01` | NOT_RUN | `ASX_EVAL_DEVELOPMENT_ROOT` was not provided |

## Sealed holdout

| Check | Status | Result |
|---|---|---|
| `../../.venv/bin/python evals/run_gold_evals.py --format markdown --estimated-case-cost-aud 0.01` | NOT_RUN | `ASX_EVAL_HOLDOUT_ROOT` was not provided |

The sealed labels remain outside the repository and runtime. A blind report can be produced when the external bundle is supplied, but a release decision requires the external grader.

## Credentialed Live smoke

| Check | Status | Result |
|---|---|---|
| Live providers and Gemini synthesis | NOT_RUN | EODHD, Marketstack, Tavily and Gemini credentials were not configured for this checkout |

## Release conclusion

The local recorded release candidate passes its executable test, lint, synthetic-evaluation and frontend gates. It is not Live validated. The external development corpus, sealed holdout and credentialed Live smoke must each pass their own gates before the product can claim a Live release.
