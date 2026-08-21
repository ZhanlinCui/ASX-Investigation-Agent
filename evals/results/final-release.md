# Final Release Record

**Recorded:** 21 August 2026 AEST<br>
**Candidate:** `v0.1.0-rc.1`<br>
**Decision:** RELEASE CANDIDATE; STABLE RELEASE NOT APPROVED

This is the single current release-status record. Historical evaluation files preserve evidence available at earlier milestones. `NOT_RUN` is not a pass.

## P5.6A local packaging gates

| Gate | Status | Fresh evidence |
| --- | --- | --- |
| Python suite | `PASS` | 332 tests passed; six third-party deprecation warnings |
| Python compile | `PASS` | `compileall` completed for `src` |
| Python lint | `PASS` | Ruff passed for `src`, `tests` and `evals` |
| Recorded policy sentinels | `PASS` | 24/24 synthetic cases passed |
| External-gold command semantics | `PASS` | Missing development and holdout roots returned `NOT_RUN` |
| Frontend lint | `PASS` | ESLint 10 passed for TypeScript and React sources |
| Frontend tests | `PASS` | Seven tests passed |
| Frontend production build | `PASS` | TypeScript and Vite build passed |
| Documentation and repository audit | `PASS` | Local links, status consistency, placeholders, stale root paths and common credential shapes checked |
| Public-boundary regressions | `PASS` | Report, archive, version, SSE, Markdown and static-DOM suites exclude private evidence/model/provider state |
| Visual responsiveness | `PASS` | Real recorded case checked at 1440, 1024, 768 and 390px with no horizontal overflow |
| Keyboard and focus semantics | `PASS` | Tab roles/order, evidence-dialog focus and Escape behavior verified in implementation and product QA |
| Clean checkout | `PASS` | Isolated install, complete local gates and recorded-case execution use repository-only inputs |

The 24 recorded cases test contracts and safety behavior. They do not measure historical attribution accuracy. The local test count is engineering evidence, not an accuracy claim.

## External release gates

| Gate | Status | Required input |
| --- | --- | --- |
| 24-case development corpus | `NOT_RUN` | External adjudicated point-in-time bundles and configured measured Gemini path |
| 12-case sealed holdout | `NOT_RUN` | Separately controlled blind corpus, labels and grader |
| Credentialed Live investigation | `NOT_RUN` | Rotated credentials, provider entitlements and completed-session canaries |

## Decision rule

P5.6A authorizes a public release-candidate tag and GitHub pre-release. It does not approve a stable release. Stable approval requires all three external gates to report `PASS`, zero hard-safety failures, the documented attribution and abstention thresholds, per-case latency and measured AUD cost, and a reviewed ordinal confidence artifact.

Confidence remains an `UNCALIBRATED` `LOW / MEDIUM / HIGH` evidence-strength band, not a probability.
