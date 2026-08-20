# ASX Investigation Agent Architecture Dossier Design

## Deliverable

Create one English architecture dossier of no more than ten pages. The target is nine A4 landscape pages. Deliver the editable LaTeX source and the compiled PDF. The PDF describes the intended product architecture and labels the repository's present implementation status honestly.

Final files:

- `docs/architecture/asx-investigation-agent-architecture.tex`
- `output/pdf/asx-investigation-agent-architecture.pdf`

Supporting LaTeX files may live beside the main source when they make diagrams or styling easier to maintain. Rendered QA images belong under `tmp/pdfs/` and are not deliverables.

## Reader and Purpose

The primary reader is a senior product, engineering, data, or AI reviewer assessing whether the design can support unseen ASX investigation cases. The dossier must let that reader understand the product contract, inspect the main technical boundaries, challenge the evidence and confidence logic, and see how the system would be evaluated.

The document is an architecture blueprint, not evidence that the software has been built. It must distinguish these states:

- Design baseline: the committed product and development documents.
- Repository scaffold: untracked package, test, and web configuration files visible on 20 August 2026.
- Verified current state: `pytest -q` stops during collection because the investigation package is absent.
- Target state: the system described by the architecture diagrams and release gates.

## Page Architecture

### Page 1: Cover and Executive Thesis

Use a restrained cover with a compact visual that links market movement, point-in-time evidence, causal validation, calibrated confidence, and a cited result. State the design thesis in one sentence and list the four owned decisions: tools, context, memory, and evaluation.

### Page 2: Product Contract and ASX Constraints

Show the input-to-output contract as a requirements map. Include ASX ordinary equities, ticker plus ASX date, AUD rendering, AEST/AEDT rendering, ASX session rules, point-in-time eligibility, evidence-linked claims, conflict visibility, and explicit abstention. Separate goals, non-goals, and required result states.

### Page 3: System Context and Layered Architecture

Use a UML/C4-style component diagram showing the workbench or API, investigation service, deterministic truth layer, provider gateway, evidence system, two LLM nodes, confidence and citation gates, storage, and external sources. Mark trust boundaries and the distinction between deterministic computation and model reasoning.

### Page 4: Agent Runtime and Investigation State Machine

Combine a runtime flow and state machine. Show instrument and session resolution, market forensics, corporate-action checks, evidence discovery, registry construction, hypothesis generation, deterministic validation, critic review, one bounded targeted-retrieval loop, claim construction, calibration, citation validation, and report rendering. Show terminal outcomes for completed, no identifiable catalyst, insufficient evidence, incomplete data, and failure.

### Page 5: Tool, Source, Conflict, and Context Architecture

Show typed provider interfaces for market data, ASX disclosures, corporate actions, news, macro, commodity, FX, and document retrieval. Visualize provider outcome semantics, source tiers, field-aware precedence, explicit disagreement, immutable snapshots, metadata filtering, hybrid passage retrieval, deduplication by origin, and bounded evidence packs. Make clear that provider failure is not an empty result and retrieved text is untrusted data.

### Page 6: Memory Model and Isolation Boundaries

Use a partition diagram covering case state, persistent reference memory, content-addressed cache, calibration artifacts, and sealed evaluation assets. Show allowed writes, versioning, retention, and retrieval gates. Mark previous narratives, rumours, model conclusions, hidden holdout labels, prompts containing secrets, and cross-case causal priors as prohibited memory.

### Page 7: Claim-Evidence Graph and Confidence Pipeline

Show a typed claim-evidence graph with supporting, contradicting, quantitative, and retrospective edges. Place the confidence pipeline beside it: observable features, deterministic caps, calibrator, confidence band, completeness, and abstention. Keep anomaly score, claim support, selected-hypothesis confidence, and investigation completeness separate. Include Brier score and ECE in compact notation.

### Page 8: Evaluation Architecture and Release Gates

Show development, calibration, and sealed holdout splits with issuer and time separation. Connect recorded fixtures and live checks to deterministic, retrieval, attribution, grounding, temporal, calibration, abstention, latency, and cost graders. Include the initial release gates from the master plan and a failure taxonomy. State that target thresholds are not current results.

### Page 9: Deployment, Security, Observability, and Roadmap

Use a deployment diagram for client, API, workers, provider gateway, model gateway, relational case store, immutable object storage, telemetry, and secrets. Overlay the main trust boundaries and security controls. End with the M0-M9 delivery sequence, current-state marker, critical risks, and the rationale for the four owned decisions.

## Visual System

Use the product design palette: warm paper background, near-black ink, graphite metadata, teal as the main accent, green for valid or supporting states, amber for partial states, and brick red for conflicts or failures. Use a clean sans-serif for titles and body text, tabular numerals, thin rules, rounded cards, and restrained shadows where LaTeX rendering permits.

Each page must have one dominant visual, two to four short explanation blocks, a page title, and a footer with document version and page number. Dense tables are allowed only when they clarify exact mappings or gates. No page may become an essay. Diagrams must remain vector graphics in the PDF and must use legible labels at normal viewing size.

## Content Rules

- Use concise professional English.
- Do not claim that planned capabilities or target metrics are implemented.
- Do not use model self-confidence as the final confidence score.
- Do not present factor residuals as causal attribution.
- Do not treat later commentary as contemporaneous causal evidence.
- Do not collapse conflicting source values into an average.
- Keep every monetary example in AUD and every displayed local timestamp in AEST or AEDT.
- Define abbreviations on first use and include a compact glossary only if space permits.
- Cite primary or authoritative sources for market rules and technical standards. Keep citations compact enough for the nine-page limit.

## Acceptance Criteria

- The compiled PDF contains exactly nine pages and no content is clipped, overlapped, missing, or illegible.
- The PDF contains detailed system, runtime, data, memory, confidence, evaluation, and deployment diagrams.
- The four assignment decisions are explicitly answered.
- The target architecture is traceable to the repository's product design and master plan.
- Current state, target state, and release gates are visibly distinct.
- The LaTeX source compiles without errors in the documented build command.
- PDF text extraction contains the page titles and no placeholder text.
- Rendered page images pass visual inspection at full-page and enlarged views.
