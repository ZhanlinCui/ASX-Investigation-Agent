import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import App, { ReportView, type Report } from "./App";
import { toSydneyIso } from "./time";

describe("App", () => {
  it("renders an English investigation workspace", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("ASX Investigator");
    expect(html).toContain("Investigate a market move");
    expect(html).toContain("All values AUD · ASX trading calendar");
    expect(html).toContain("Source published (Sydney)");
  });

  it("serializes source publication time with the correct Sydney offset", () => {
    expect(toSydneyIso("2026-08-20T08:00")).toBe("2026-08-20T08:00:00+10:00");
    expect(toSydneyIso("2026-01-20T08:00")).toBe("2026-01-20T08:00:00+11:00");
  });

  it("shows evidence provenance without rendering a probability", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("Artifact SHA-256");
    expect(html).not.toContain("confidence probability");
  });

  it("shows causal evidence and calibration status without chain of thought", () => {
    const report = completedReport();
    const html = renderToStaticMarkup(<ReportView report={report} onRefined={() => undefined} />);

    expect(html).toContain("Evidence assertions");
    expect(html).toContain("Mechanism tests");
    expect(html).toContain("Decision ledger");
    expect(html).toContain("Calibration sample status");
    expect(html).toContain("Open exact passage");
    expect(html).toContain("NOT RUN");
    expect(html).not.toMatch(/chain of thought/i);
    expect(html).not.toContain("Probability:");
  });
});

function completedReport(): Report {
  return {
    case_id: "CASE-1", run_id: "VERSION-1", case_version: 1, status: "COMPLETED", outcome: "EXPLAINED",
    ticker: "BHP", trade_date: "2026-08-20", timezone_label: "AEST",
    instrument: { company_name: "BHP Group", sector: "Materials" },
    market_move: { close_return_pct: 2.1, open_gap_pct: 1.2, open_to_close_pct: 0.8, turnover_aud: 1200000 },
    assessment: { primary_claim_id: "C1", summary: "An audited issuer event explains the recorded move." },
    claims: [{ claim_id: "C1", claim_type: "CAUSE", text: "A recorded issuer event supported the move." }],
    evidence: [{ evidence_id: "E1", source_name: "Issuer", source_url: "https://example.test/e1", published_at: "2026-08-20T07:00:00+10:00", authority: "PRIMARY", title: "Trading update", passage: "Production guidance was raised.", role: "CAUSAL_INPUT", locator: "p. 1" }],
    hypotheses: [], validation_results: [], coverage_gaps: [], conflicts: [],
    confidence: { band: "HIGH", calibration_status: "UNCALIBRATED", positive_factors: [], negative_factors: [], applied_caps: [], rule_version: "confidence-v1" },
    completeness: { status: "COMPLETE", required_capabilities: [], missing_capabilities: [] },
    coverage_status: "COMPLETE", source_policy_version: "phase3-v1", model_configuration: {}, provider_diagnostics: [], artifact_hashes: [], checkpoint_lineage: [], trace: [],
    assertions: [{ assertion_id: "A1", evidence_id: "E1", exact_text: "Production guidance was raised.", span_hash: "a".repeat(64), artifact_hash: "b".repeat(64), locator: "p. 1", role: "CAUSAL_INPUT", causal_eligible: true, mechanism_hint: "ISSUER_EVENT" }],
    mechanism_tests: [{ test_id: "MT-ISSUER", mechanism: "ISSUER_EVENT", status: "PASS", summary: "Eligible audited assertion is present.", policy_version: "phase3-p3.2-v1", supporting_assertion_ids: ["A1"], contradicting_assertion_ids: [] }],
    ledger: [{ sequence: 1, stage: "resolve_instrument", status: "COMPLETED", input_hashes: ["c".repeat(64)], output_hashes: ["d".repeat(64)], policy_version: "phase3-p3.2-v1", created_at: "2026-08-20T08:00:00+10:00" }],
    calibration_metadata: { label: "Evidence-strength band calibration", status: "NOT_RUN", bands: {} },
  };
}
