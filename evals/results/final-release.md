# Final Release Record

**Recorded:** 21 August 2026 (AEST)
**Decision:** RELEASE CANDIDATE

This is the single current release-status record. Historical evaluation files preserve the evidence available at earlier milestones. `NOT_RUN` is not a pass.

## Verified local baseline

| Gate | Status | Evidence |
|---|---|---|
| Python suite | PASS | 324 tests passed; six third-party deprecation warnings |
| Python lint | PASS | Ruff passed for `src`, `tests` and `evals` |
| Frontend tests | PASS | Six tests passed |
| Frontend production build | PASS | TypeScript and Vite build passed |
| Recorded policy sentinels | PASS | 24 synthetic policy cases passed |

The synthetic cases test contracts and safety behavior. They do not measure historical attribution accuracy.

## External release gates

| Gate | Status | Reason |
|---|---|---|
| 24-case development corpus | NOT_RUN | External point-in-time corpus was not supplied |
| 12-case sealed holdout | NOT_RUN | External blind corpus and grader were not supplied |
| Credentialed Live investigation | NOT_RUN | Release credentials and completed Live canaries were not supplied |

## Decision rule

The repository may publish a release candidate after its local product-packaging gates pass. A stable release requires all three external gates to report `PASS`, including zero hard-safety failures and the documented attribution and abstention thresholds.
