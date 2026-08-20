# ASX Investigation Agent Architecture Dossier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a visually led, exactly nine-page English architecture dossier as editable LaTeX and a verified PDF.

**Architecture:** A single A4 landscape LaTeX document uses TikZ for vector diagrams and fixed page canvases for predictable pagination. Each page owns one architecture concern and one dominant visual. The content is derived from the committed design baseline, with authoritative external references used only for market rules, AI risk, security, and calibration guidance.

**Tech Stack:** LaTeX, Tectonic 0.16.9, TikZ/PGF, tcolorbox, tabularx, fontspec, hyperref, Poppler, pdfplumber.

## Global Constraints

- The final PDF must contain exactly nine pages and remain below the user limit of ten pages.
- The document language is professional, concise English.
- The document is primarily visual, with short segmented explanations.
- Current implementation state, target architecture, and release targets must never be conflated.
- All monetary examples are in AUD and all displayed local timestamps use AEST or AEDT.
- All diagrams remain vector graphics in the PDF.
- No Agent implementation code is changed.

---

### Task 1: Authoritative Inputs and Build Tool

**Files:**
- Create: `tmp/tools/tectonic`
- Create: `docs/architecture/references.md`

**Interfaces:**
- Consumes: committed repository documents and public authoritative sources.
- Produces: a pinned compiler and a compact source ledger used by the dossier.

- [ ] **Step 1: Install the pinned standalone compiler locally**

Download `tectonic-0.16.9-aarch64-apple-darwin.tar.gz` from the official Tectonic GitHub release `tectonic@0.16.9`, extract only the `tectonic` executable into `tmp/tools/`, and run `tmp/tools/tectonic --version`.

Expected: output contains `tectonic 0.16.9`.

- [ ] **Step 2: Record authoritative references**

Write `docs/architecture/references.md` with the source title, organization, access date, URL, and the exact design claim supported by each source. Include the ASX cash-market hours and calendar, NIST AI RMF and Generative AI Profile, OWASP prompt-injection guidance, and scikit-learn probability-calibration guidance.

- [ ] **Step 3: Verify the source ledger**

Run:

```bash
rg -n 'ASX|NIST|OWASP|scikit-learn|https://' docs/architecture/references.md
```

Expected: every organization and every URL appears at least once.

### Task 2: LaTeX Design System and Page Skeleton

**Files:**
- Create: `docs/architecture/asx-investigation-agent-architecture.tex`

**Interfaces:**
- Consumes: the approved page architecture and product visual tokens.
- Produces: fixed page helpers, typography, palette, diagram styles, headers, and footers used by all pages.

- [ ] **Step 1: Build the preamble and visual primitives**

Define A4 landscape geometry, system sans-serif fonts, the warm-paper palette, teal/green/amber/brick semantic colors, TikZ libraries, card styles, node styles, arrow styles, status pills, page headers, and page footers. Add macros for `\PageTitle`, `\DecisionCard`, `\Metric`, and `\SourceNote`.

- [ ] **Step 2: Add nine explicit page canvases**

Create one fixed-height page block for each approved page and place `\newpage` between blocks. Add the final PDF metadata title, subject, author, keywords, and version `1.0` dated `20 August 2026`.

- [ ] **Step 3: Compile the skeleton**

Run:

```bash
mkdir -p output/pdf tmp/pdfs/build
tmp/tools/tectonic -X compile docs/architecture/asx-investigation-agent-architecture.tex --outdir tmp/pdfs/build
```

Expected: exit code 0 and a PDF in `tmp/pdfs/build/`.

### Task 3: Product and Core Architecture Pages

**Files:**
- Modify: `docs/architecture/asx-investigation-agent-architecture.tex`

**Interfaces:**
- Consumes: the product design baseline, master development plan, and verified ASX market rules.
- Produces: pages 1-3.

- [ ] **Step 1: Build page 1**

Add the cover, the thesis `Deterministic market truth constrains model reasoning; evidence and calibration determine what may be claimed`, a five-stage investigation visual, and the four owned decisions.

- [ ] **Step 2: Build page 2**

Add the ticker-and-date input contract, required structured outputs, ASX time and currency constraints, point-in-time rule, explicit terminal states, and non-goals. Use a requirements map and a compact lifecycle strip.

- [ ] **Step 3: Build page 3**

Add the system context and layered component architecture. Show external sources, provider gateway, deterministic truth layer, evidence layer, Investigator and Critic nodes, validation gates, API/workbench, stores, and trust boundaries.

- [ ] **Step 4: Compile and inspect page count**

Run the Tectonic compile command and `pdfinfo tmp/pdfs/build/asx-investigation-agent-architecture.pdf | rg '^Pages:'`.

Expected: compilation succeeds; the skeleton remains nine pages.

### Task 4: Runtime, Context, and Memory Pages

**Files:**
- Modify: `docs/architecture/asx-investigation-agent-architecture.tex`

**Interfaces:**
- Consumes: the investigation graph, provider protocol, evidence registry, context pipeline, and memory rules from the design baseline.
- Produces: pages 4-6.

- [ ] **Step 1: Build page 4**

Add a UML activity flow for the full investigation, a state machine for running, targeted retrieval, completed, abstained, incomplete, and failed states, plus the bounded-loop invariants.

- [ ] **Step 2: Build page 5**

Add typed tool families, provider result semantics, field-aware disagreement handling, immutable snapshots, origin-based deduplication, metadata filtering, hybrid retrieval, and the bounded Evidence Pack. Use separate trusted-code and untrusted-content lanes.

- [ ] **Step 3: Build page 6**

Add the memory partition diagram for case state, reference memory, cache, calibration artifacts, and sealed eval assets. Draw allowed flows and prohibited cross-case priors. State versioning, retention, deletion, and access rules.

- [ ] **Step 4: Compile and scan warnings**

Run Tectonic with `--keep-logs`, then search the log for `Overfull`, `Underfull`, `Error`, and `Warning`.

Expected: no compilation error and no material overfull box.

### Task 5: Confidence, Evaluation, and Deployment Pages

**Files:**
- Modify: `docs/architecture/asx-investigation-agent-architecture.tex`

**Interfaces:**
- Consumes: the claim model, confidence design, evaluation gates, deployment requirements, and current repository evidence.
- Produces: pages 7-9 and the compact source notes.

- [ ] **Step 1: Build page 7**

Add the claim-evidence graph and confidence pipeline. Show supporting, contradicting, quantitative, and retrospective evidence roles; observable scoring features; deterministic caps; calibration; confidence bands; completeness; and abstention. Include compact Brier score and ECE equations.

- [ ] **Step 2: Build page 8**

Add the development/calibration/blind data split, recorded/live lanes, grader stack, failure taxonomy, and all initial release gates. Label every threshold `target, not current result`.

- [ ] **Step 3: Build page 9**

Add the deployment and trust-boundary diagram, security and telemetry controls, M0-M9 roadmap, current-state marker, critical risks, and one-sentence rationales for tools, context, memory, and evaluation.

- [ ] **Step 4: Copy the built artifact to the final path**

Run:

```bash
cp tmp/pdfs/build/asx-investigation-agent-architecture.pdf output/pdf/asx-investigation-agent-architecture.pdf
```

Expected: the final PDF exists at the approved stable path.

### Task 6: Structural, Textual, and Visual QA

**Files:**
- Modify if required: `docs/architecture/asx-investigation-agent-architecture.tex`
- Rebuild: `output/pdf/asx-investigation-agent-architecture.pdf`
- Create: `tmp/pdfs/rendered/`
- Create: `docs/architecture/qa-report.md`

**Interfaces:**
- Consumes: the complete source and compiled PDF.
- Produces: a verified nine-page final artifact.

- [ ] **Step 1: Run structural checks**

Run `pdfinfo` and require exactly nine pages, A4 landscape dimensions, valid metadata, and no encrypted output. Extract text with `pdftotext` or `pdfplumber` and require all nine page titles, the four owned decisions, every target metric label, and the current-state disclaimer.

- [ ] **Step 2: Run source checks**

Search the LaTeX source and extracted text for `TBD`, `TODO`, `FIXME`, fake URLs, non-ASCII dash characters, and uncited external assertions. Run `git diff --check` on the created documentation files.

- [ ] **Step 3: Render every page**

Run:

```bash
mkdir -p tmp/pdfs/rendered
pdftoppm -png -r 150 output/pdf/asx-investigation-agent-architecture.pdf tmp/pdfs/rendered/page
```

Expected: nine PNG files.

- [ ] **Step 4: Inspect the rendered pages**

Create a contact sheet and inspect it, then inspect any dense page at full resolution. Check typography, clipping, arrow routing, contrast, whitespace, footer consistency, line wrapping, and diagram legibility. Fix defects in LaTeX and repeat compile, copy, render, and inspection until clean.

- [ ] **Step 5: Run final verification**

Re-run compilation, page-count inspection, text assertions, placeholder scan, source checks, and rendering from the final source. Record the commands and results in `docs/architecture/qa-report.md`.
