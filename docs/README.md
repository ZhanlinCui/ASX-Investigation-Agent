# Documentation

This index separates the current product contract from implementation history. Current documents describe the shipped release-candidate code. Phase plans and engineering records explain how it was built. Reference material does not override the current contract.

## Current product

- [Product](product.md) — users, problem, workflow, capabilities and boundaries
- [Product design](product-design.md) — current English workbench and interaction rules
- [Architecture](architecture.md) — Agent kernel, retrieval, evidence, memory, confidence and recovery
- [Evaluation](evaluation.md) — datasets, graders, calibration and release gates
- [Release status](release-status.md) — verified local state and external prerequisites
- [Four core decisions](decisions/four-core-decisions.md) — concise rationale for tools, context, memory and evals
- [Master development plan](../MASTER_DEVELOPMENT_PLAN.md) — roadmap and gate ownership

## Active delivery record

- [Phase 5: Recall and Release Closure](phase-plans/phase-05-recall-and-release-closure.md)
- [Final release record](../evals/results/final-release.md)

## Historical phase records

- [Phase 2: Evidence-Complete Live Investigation](phase-plans/phase-02-evidence-complete-live-investigation.md)
- [Phase 3: Causal Investigation Intelligence](phase-plans/phase-03-causal-investigation-intelligence.md)
- [Phase 4: Live Validation Activation](phase-plans/phase-04-live-validation-activation.md)
- [`docs/superpowers/`](superpowers/) — approved implementation plans and design records

## Architecture dossier

- [Architecture PDF](assets/asx-investigation-agent-architecture.pdf)
- [LaTeX source](architecture/asx-investigation-agent-architecture.tex)
- [QA record](architecture/qa-report.md)
- [Source references](architecture/references.md)

## Reference only

- [Original R&D specification](reference/original-rd-specification.md) — an extensive early design exploration retained for context; it is not a current implementation-status document.

When documents disagree, the public schemas and tests take precedence over historical records, while this index, the master plan and release status define current product claims.
