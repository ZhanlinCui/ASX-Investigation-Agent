# ASX Investigation Agent Architecture Dossier QA Report

Date: 20 August 2026

## Historical artifact

- Source: `docs/architecture/asx-investigation-agent-architecture.tex`
- PDF: `docs/assets/asx-investigation-agent-architecture.pdf`
- Compiler: Tectonic 0.16.9
- Verified command: `tmp/tools/tectonic -X compile docs/architecture/asx-investigation-agent-architecture.tex --outdir tmp/pdfs/build --keep-logs`
- Rebuild with an installed compiler: `tectonic -X compile docs/architecture/asx-investigation-agent-architecture.tex --outdir docs/assets`

This dossier records the architecture at the 20 August 2026 review point. The current implementation contract is `docs/architecture.md`; this QA record does not make a current release claim.

## Structural checks

| Check | Result |
|---|---|
| Compile exit status | Passed |
| Page count | 9 |
| Page format | A4 landscape, 841.89 x 595.28 pt |
| Encryption | None |
| JavaScript | None |
| Raster image XObjects | 0 |
| Fonts | All PDF font resources embedded |
| Page text extraction | Non-empty on all nine pages |
| Required page titles | All nine present |
| Required decisions | Tools, context, memory and evaluation present |
| Target-state disclaimer | Present |
| Evaluation target disclaimer | Present |
| Placeholder and fake-token scan | No findings |
| TeX overfull or underfull boxes | No findings |

The TeX build reports that Arial is loaded from the macOS system font directory. The compiled PDF embeds the used Arial subsets. It also reports small-size substitutions for compact math notation on the confidence and evaluation pages; the rendered equations remain legible at 150 dpi and under enlarged inspection.

## Visual checks

All nine pages were rendered with Poppler at 150 dpi. Each page was inspected for clipping, overlap, line wrapping, contrast, whitespace, arrow routing, footer consistency and diagram legibility.

Corrections made during visual QA:

- Separated the calibration and lifecycle-control cards on the memory page.
- Moved the evaluation current-state disclaimer to its own line.
- Raised and shortened the final-page rationale card.
- Separated the roadmap, current-state marker, source note and footer on the final page.

The final render shows no clipped or overlapping content. All architecture diagrams are PDF vector graphics rather than embedded raster images.

## Content checks

- Current runnable-MVP state is separated from the target architecture and from production-readiness claims.
- No target release metric is presented as an observed result.
- Provider failure is distinct from an empty successful response.
- Later evidence is restricted to retrospective context for earlier moves.
- Market anomaly, claim support, selected-hypothesis confidence and investigation completeness remain separate concepts.
- Memory excludes previous narratives and sealed holdout labels from production priors.
- The four required design decisions are answered on the cover and final page.
- External market, governance, security and calibration claims map to `docs/architecture/references.md`.
- Repository status on the rendered dossier reflects historical revision `ca128bc`: 12 passing Python tests and one passing recorded regression case. Current results are maintained separately in `evals/results/final-release.md`; confidence remains labelled `UNCALIBRATED` and no blind performance result is claimed.
