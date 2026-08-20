import { FormEvent, useEffect, useState } from "react";
import {
  ArrowClockwise,
  BookOpenText,
  CaretRight,
  ChartLineUp,
  CheckCircle,
  ClipboardText,
  Clock,
  DownloadSimple,
  FileArrowUp,
  FileText,
  MagnifyingGlass,
  ShieldCheck,
  Sparkle,
  WarningCircle,
  X,
} from "@phosphor-icons/react";

import { toSydneyIso } from "./time";

type Status = "IDLE" | "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED_RECOVERABLE" | "FAILED";
type Stage = { sequence: number; stage: string; status: string };
type Evidence = { evidence_id: string; source_name: string; source_host?: string | null; published_at: string; retrieved_at: string; authority: string; title: string; role: string; content_hash: string; locator?: string | null; page?: number | null; content_endpoint: string };
type Hypothesis = { hypothesis_id: string; rank: number; status: string; driver_label: string; statement: string; supporting_evidence_ids: string[]; contradicting_evidence_ids: string[] };
type Validation = { validation_id: string; kind: string; status: string; evidence_ids: string[] };
type Gap = { gap_id: string; capability: string; provider: string; retryable: boolean };
type Conflict = { conflict_id: string; field: string; primary_source: string; primary_value: string; secondary_source: string; secondary_value: string; resolution: string };
type Assertion = { assertion_id: string; evidence_id: string; span_hash: string; artifact_hash: string; locator?: string | null; role: string; causal_eligible: boolean; mechanism_hint: string; content_endpoint: string };
type MechanismTest = { test_id: string; mechanism: string; status: string; summary: string; policy_version: string; supporting_assertion_ids: string[]; contradicting_assertion_ids: string[] };
type LedgerEntry = { sequence: number; stage: string; status: string; input_hashes: string[]; output_hashes: string[]; policy_version: string; created_at: string; schema_version?: string; validation_status?: string };
type CalibrationBand = { eligible_cases: number; material_errors: number; status: string };
type CalibrationMetadata = { label: string; status: string; corpus_version?: string; confidence_rule_version?: string; bands: Record<string, CalibrationBand> };
type ReleaseGate = { name: string; status: "PASS" | "FAIL" | "NOT_RUN"; detail: string };

export type Report = {
  case_id: string; run_id: string; case_version: number; parent_version_id?: string; status: Status; outcome: string;
  ticker: string; trade_date: string; timezone_label: string;
  instrument: { asx_code: string; company_name: string; exchange: string; currency: string; sector?: string | null };
  market_move?: { close_return_pct: number; open_gap_pct: number; open_to_close_pct: number; turnover_aud: number; volume_zscore?: number | null; return_zscore?: number | null; market_relative_return_pct?: number | null; is_unusual: boolean; resolution: string } | null;
  assessment: { primary_claim_id?: string; summary: string };
  claims: Array<{ claim_id: string; claim_type: string; text: string; supporting_evidence_ids: string[]; contradicting_evidence_ids: string[] }>;
  evidence: Evidence[]; hypotheses: Hypothesis[]; validation_results: Validation[]; coverage_gaps: Gap[]; conflicts: Conflict[];
  confidence: { band: string; calibration_status: string; positive_factors: string[]; negative_factors: string[]; applied_caps: string[]; rule_version: string };
  completeness: { status: string; required_capabilities: string[]; missing_capabilities: string[] };
  coverage_status: string; source_policy_version: string;
  assertions: Assertion[]; mechanism_tests: MechanismTest[]; ledger: LedgerEntry[]; calibration_metadata: CalibrationMetadata;
  release_gates?: ReleaseGate[];
};

type ArchiveItem = { case_id: string; version_id: string; version_number: number; parent_version_id?: string | null; ticker: string; trade_date: string; mode: string; status: string; outcome?: string | null; active_stage?: string | null; confidence_band?: string; evidence_count?: number; completeness_status?: string };

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const terminalStatuses = ["COMPLETED", "FAILED_RECOVERABLE", "FAILED"];

function percent(value?: number) { return value === undefined ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`; }
function aud(value?: number) { return value === undefined ? "—" : `AUD ${new Intl.NumberFormat("en-AU", { maximumFractionDigits: 0 }).format(value)}`; }
function human(value: string) { return value.replaceAll("_", " "); }
function confidenceTone(band?: string) { return band === "HIGH" ? "high" : band === "MEDIUM" ? "medium" : "low"; }

export default function App() {
  const [ticker, setTicker] = useState("BHP");
  const [tradeDate, setTradeDate] = useState("2026-08-20");
  const [mode, setMode] = useState("RECORDED");
  const [status, setStatus] = useState<Status>("IDLE");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [stages, setStages] = useState<Stage[]>([]);
  const [archive, setArchive] = useState<ArchiveItem[]>([]);
  const [sourceIds, setSourceIds] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [sourcePublishedAt, setSourcePublishedAt] = useState("2026-08-20T08:00");

  async function refreshArchive() {
    try {
      const response = await fetch(`${apiBase}/api/v1/investigations`);
      if (response.ok) setArchive(((await response.json()) as { items: ArchiveItem[] }).items);
    } catch { /* The investigation form remains usable while the API reconnects. */ }
  }
  useEffect(() => { void refreshArchive(); }, []);

  useEffect(() => {
    if (!caseId) return;
    const stream = new EventSource(`${apiBase}/api/v1/investigations/${caseId}/events`);
    stream.addEventListener("status", (event) => setStatus(JSON.parse(event.data).status as Status));
    stream.addEventListener("stage", (event) => {
      const item = JSON.parse(event.data) as Stage;
      setStages((current) => [...current.filter((value) => !(value.stage === item.stage && value.status === item.status)), item]);
    });
    stream.addEventListener("completed", () => stream.close());
    stream.addEventListener("failed", () => stream.close());
    return () => stream.close();
  }, [caseId]);

  useEffect(() => {
    if (!caseId || !["QUEUED", "RUNNING"].includes(status)) return;
    const timer = window.setInterval(async () => {
      const response = await fetch(`${apiBase}/api/v1/investigations/${caseId}`);
      if (!response.ok) return;
      const payload = (await response.json()) as Report & { error?: string };
      setStatus(payload.status);
      if (payload.status === "COMPLETED") { setReport(payload); void refreshArchive(); }
      if (payload.status === "FAILED_RECOVERABLE") setError(payload.error ?? "Investigation failed at a recoverable stage.");
    }, 450);
    return () => window.clearInterval(timer);
  }, [caseId, status]);

  async function investigate(event: FormEvent) {
    event.preventDefault(); setError(null); setReport(null); setStages([]); setStatus("QUEUED");
    try {
      const response = await fetch(`${apiBase}/api/v1/investigations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker, trade_date: tradeDate, mode, source_ids: sourceIds }) });
      if (!response.ok) throw new Error("Check the ASX code, session date, and configured sources.");
      setCaseId(((await response.json()) as { case_id: string }).case_id);
    } catch (caught) { setStatus("FAILED_RECOVERABLE"); setError(caught instanceof Error ? caught.message : "Could not start investigation."); }
  }

  async function openCase(item: ArchiveItem) {
    const response = await fetch(`${apiBase}/api/v1/investigations/${item.case_id}`);
    if (!response.ok) return;
    const payload = (await response.json()) as Report & { error?: string };
    setCaseId(item.case_id); setStatus(payload.status); setError(payload.error ?? null); setStages([]);
    setReport(payload.status === "COMPLETED" ? payload : null);
  }

  async function uploadSource(file?: File) {
    if (!file) return;
    setUploading(true); setError(null);
    try {
      const body = new FormData(); body.append("file", file); body.append("title", file.name); body.append("published_at", toSydneyIso(sourcePublishedAt)); body.append("is_official", "false");
      const response = await fetch(`${apiBase}/api/v1/sources/upload`, { method: "POST", body });
      if (response.ok) {
        const source = (await response.json()) as { source_id: string };
        setSourceIds((current) => [...current, source.source_id]);
      }
      else setError("The source could not be frozen. Use PDF or text up to 20 MB.");
    } catch { setError("The source could not be frozen because the API is unavailable."); }
    finally { setUploading(false); }
  }

  const active = status === "QUEUED" || status === "RUNNING";
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">A</span><span>ASX Investigator</span></div>
      <nav aria-label="Primary"><a className="nav-item active" href="#investigate"><MagnifyingGlass size={18} /> Investigate</a><a className="nav-item" href="#cases"><ClipboardText size={18} /> Case archive</a><a className="nav-item" href="#method"><BookOpenText size={18} /> Method</a></nav>
      <div id="cases" className="archive-list"><span>Recent cases</span>{archive.slice(0, 8).map((item) => <button key={item.case_id} onClick={() => void openCase(item)}><b>{item.ticker}</b><small>{item.trade_date} · v{item.version_number}</small><em>{human(item.outcome ?? item.status)}</em></button>)}</div>
      <div className="sidebar-foot"><div className="source-status"><span className="status-dot" /> Evidence-first analysis</div><p>Claims, source timing, provider gaps, and conflicts remain auditable.</p></div>
    </aside>

    <main id="investigate" className="workspace">
      <header className="topbar"><div><p className="eyebrow">MARKET INVESTIGATION</p><h1>Investigate a market move</h1></div><div className="calendar-note"><Clock size={16} /> All values AUD · ASX trading calendar</div></header>
      <section className="case-form-card" aria-label="New investigation"><form onSubmit={investigate}><label className="field-label" htmlFor="ticker">ASX code</label><div className="search-row"><div className="input-with-icon"><MagnifyingGlass size={18} /><input id="ticker" value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} maxLength={6} /></div><div className="date-field"><label className="field-label" htmlFor="date">Trading date</label><input id="date" type="date" value={tradeDate} onChange={(event) => { setTradeDate(event.target.value); setSourcePublishedAt(`${event.target.value}T08:00`); }} /></div><select aria-label="Data mode" value={mode} onChange={(event) => setMode(event.target.value)}><option value="LIVE">Live sources</option><option value="RECORDED">Recorded case</option></select><button className="primary-button" type="submit" disabled={active}>{active ? "Investigating…" : "Investigate"}<CaretRight size={16} weight="bold" /></button></div></form><div className="case-hints"><span><ShieldCheck size={16} /> AEST/AEDT timing is validated.</span><label className="source-time">Source published (Sydney)<input type="datetime-local" value={sourcePublishedAt} onChange={(event) => setSourcePublishedAt(event.target.value)} /></label><label className="upload-control"><FileArrowUp size={16} /> {uploading ? "Freezing source…" : "Add PDF or text"}<input type="file" accept="application/pdf,text/plain,text/html" onChange={(event) => void uploadSource(event.target.files?.[0])} /></label>{sourceIds.length > 0 && <span>{sourceIds.length} frozen source{sourceIds.length === 1 ? "" : "s"} attached</span>}</div></section>

      {active && <RunningTimeline status={status} stages={stages} />}
      {error && <section className="error-card"><WarningCircle size={20} /><div><strong>Investigation unavailable</strong><p>{error}</p>{caseId && status === "FAILED_RECOVERABLE" && <button className="text-button" onClick={() => void fetch(`${apiBase}/api/v1/investigations/${caseId}/retry`, { method: "POST" }).then((response) => { if (response.ok) { setError(null); setStatus("QUEUED"); } })}><ArrowClockwise size={15} /> Retry</button>}</div></section>}
      {!report && !active && !error && <EmptyState onRecorded={() => { setTicker("BHP"); setTradeDate("2026-08-20"); setMode("RECORDED"); }} />}
      {report && <ReportView report={report} onRefined={(id) => { setCaseId(id); setReport(null); setStatus("QUEUED"); setStages([]); }} />}
    </main>
  </div>;
}

function RunningTimeline({ status, stages }: { status: Status; stages: Stage[] }) {
  const latest = stages.filter((item) => item.status === "RUNNING").at(-1)?.stage;
  return <section className="working-card" aria-live="polite"><div className="pulse" /><div><strong>{status === "QUEUED" ? "Preparing case" : human(latest ?? "evidence investigation")}</strong><p>Each completed stage is checkpointed for replay and recovery.</p><div className="stage-strip">{stages.filter((item) => item.status === "COMPLETED").slice(-5).map((item) => <span key={`${item.stage}-${item.sequence}`}><CheckCircle size={13} />{human(item.stage)}</span>)}</div></div></section>;
}

function EmptyState({ onRecorded }: { onRecorded: () => void }) {
  return <section className="empty-state"><div className="empty-icon"><Sparkle size={24} /></div><h2>Start with the trading session</h2><p>Observed facts stay separate from evidence-backed explanations. Missing coverage produces an abstention, not a guess.</p><div className="suggestions"><button onClick={onRecorded}>Load the recorded BHP case <CaretRight size={15} /></button><span>Live cases require configured provider credentials. Frozen provenance includes Artifact SHA-256 values.</span></div></section>;
}

export function ReportView({ report, onRefined }: { report: Report; onRefined: (caseId: string) => void }) {
  const [selected, setSelected] = useState<Evidence | null>(null);
  const [passage, setPassage] = useState<{ passage: string; locator?: string; page?: number } | null>(null);
  const [versions, setVersions] = useState<ArchiveItem[]>([]);
  const primary = report.claims.find((claim) => claim.claim_id === report.assessment.primary_claim_id);
  useEffect(() => { void fetch(`${apiBase}/api/v1/investigations/${report.case_id}/versions`).then((response) => response.json()).then((payload: { items: ArchiveItem[] }) => setVersions(payload.items)); }, [report.case_id]);
  async function inspect(item: Evidence) { setSelected(item); setPassage(null); const response = await fetch(`${apiBase}${item.content_endpoint}`); if (response.ok) setPassage(await response.json()); }
  function inspectAssertion(assertion: Assertion) { const evidence = report.evidence.find((item) => item.evidence_id === assertion.evidence_id); if (evidence) void inspect(evidence); }
  async function refine(options: { primary_only?: boolean; excluded_evidence_ids?: string[] }) { const response = await fetch(`${apiBase}/api/v1/investigations/${report.case_id}/versions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(options) }); if (response.ok) onRefined(((await response.json()) as { case_id: string }).case_id); }
  const parent = versions.find((item) => item.version_id === report.parent_version_id);
  return <div className="report-stack">
    <section className="report-head"><div><p className="eyebrow">CASE RESULT · VERSION {report.case_version}</p><h2>{report.instrument.company_name} <span>({report.ticker})</span></h2><p>{report.trade_date} · {report.timezone_label} · {report.instrument.sector ?? "ASX-listed equity"}</p><div className="outcome-line"><span>{human(report.outcome)}</span><span>{human(report.status)}</span></div></div><div className={`confidence ${confidenceTone(report.confidence.band)}`}><span>Selected hypothesis</span><strong>{report.confidence.band}</strong><small>{report.confidence.calibration_status} · {report.confidence.rule_version}</small></div></section>
    <div className="report-actions"><a href={`${apiBase}/api/v1/investigations/${report.case_id}?format=markdown`}><DownloadSimple size={15} /> Export Markdown</a><button onClick={() => void refine({ primary_only: true })}><FileText size={15} /> Primary-sources-only child</button></div>
    {parent && <section className="comparison-bar"><b>Compared with v{parent.version_number}</b><span>{human(parent.outcome ?? parent.status)} → {human(report.outcome)}</span><span>{parent.confidence_band ?? "Not published"} → {report.confidence.band}</span><span>{parent.evidence_count ?? "—"} → {report.evidence.length} evidence items</span></section>}
    <section className="metric-grid"><Metric label="Close-to-close" value={percent(report.market_move?.close_return_pct)} emphasis /><Metric label="Opening gap" value={percent(report.market_move?.open_gap_pct)} /><Metric label="Open to close" value={percent(report.market_move?.open_to_close_pct)} /><Metric label="Turnover" value={aud(report.market_move?.turnover_aud)} /><Metric label="Market relative" value={percent(report.market_move?.market_relative_return_pct ?? undefined)} /></section>
    <section className="assessment-card"><div className="section-kicker"><ChartLineUp size={18} /> Leading assessment</div><h3>{report.assessment.summary}</h3><div className="assessment-footer"><span className="chip">{primary?.claim_type ?? "UNRESOLVED"}</span><span>Coverage: {human(report.coverage_status)}</span><span>Completeness: {human(report.completeness.status)}</span>{report.confidence.applied_caps.map((cap) => <span className="caution" key={cap}>{human(cap)}</span>)}</div></section>
    <section className="analysis-grid"><Hypotheses items={report.hypotheses} validations={report.validation_results} /><ConfidencePanel report={report} /></section>
    <section className="decision-grid" aria-label="Audited causal decisions"><AssertionPanel assertions={report.assertions} onInspect={inspectAssertion} evidenceIds={new Set(report.evidence.map((item) => item.evidence_id))} /><MechanismPanel tests={report.mechanism_tests} /><LedgerPanel entries={report.ledger} /><CalibrationPanel metadata={report.calibration_metadata} gates={report.release_gates ?? missingExternalGates} /></section>
    {(report.coverage_gaps.length > 0 || report.conflicts.length > 0) && <section className="exceptions-card"><h3>Coverage and conflicts</h3><div className="exception-grid">{report.coverage_gaps.map((gap) => <article key={gap.gap_id}><WarningCircle size={18} /><div><b>{human(gap.capability)}</b><p>Coverage is incomplete for this capability.</p><small>{gap.retryable ? "Retry may be available." : "No retry is available for this recorded gap."}</small></div></article>)}{report.conflicts.map((conflict) => <article key={conflict.conflict_id}><WarningCircle size={18} /><div><b>{human(conflict.field)} conflict</b><p>{conflict.primary_source} {conflict.primary_value} · {conflict.secondary_source} {conflict.secondary_value}</p><small>{conflict.resolution}</small></div></article>)}</div></section>}
    <section className="evidence-card"><div className="section-title"><div><h3>Evidence register</h3><p>Open an item to inspect the exact stored passage and locator.</p></div><span>{report.evidence.length} item{report.evidence.length === 1 ? "" : "s"}</span></div>{report.evidence.length ? <div className="evidence-list">{report.evidence.map((item) => <button className="evidence-item" key={item.evidence_id} onClick={() => void inspect(item)}><span className="evidence-number">{item.evidence_id.split(":").at(-1)}</span><span><span className="evidence-meta"><em>{human(item.authority)}</em><em>{new Date(item.published_at).toLocaleString("en-AU", { timeZone: "Australia/Sydney", dateStyle: "medium", timeStyle: "short" })}</em><em>{human(item.role)}</em></span><b>{item.title}</b><p>Exact source text is available through the controlled passage viewer.</p><small>{item.source_host ?? item.source_name} · {item.locator ?? "Locator unavailable"}</small></span></button>)}</div> : <p className="no-evidence">No time-eligible evidence was registered.</p>}</section>
    <section id="method" className="method-note"><CheckCircle size={18} /><p>Confidence is a rule-governed evidence-strength band, not a probability. Completeness and claim support are assessed separately.</p></section>
    {selected && <div className="passage-backdrop" role="presentation" onClick={() => setSelected(null)}><aside className="passage-drawer" role="dialog" aria-modal="true" aria-label="Evidence passage" onClick={(event) => event.stopPropagation()}><button className="drawer-close" onClick={() => setSelected(null)} aria-label="Close passage"><X size={18} /></button><span className="chip">{selected.evidence_id}</span><h3>{selected.title}</h3><p className="drawer-meta">{human(selected.authority)} · {passage?.locator ?? selected.locator ?? "No locator"}</p><blockquote>{passage?.passage ?? "Exact passage unavailable for this case version."}</blockquote><div className="drawer-actions"><button onClick={() => void refine({ excluded_evidence_ids: [selected.evidence_id] })}>Exclude in child version</button></div></aside></div>}
  </div>;
}

function Hypotheses({ items, validations }: { items: Hypothesis[]; validations: Validation[] }) { return <section className="hypothesis-card"><h3>Ranked hypotheses</h3>{items.length ? items.map((item) => <article key={item.hypothesis_id}><span>{item.rank}</span><div><b>{human(item.driver_label)}</b><p>{item.statement}</p><small>{human(item.status)} · Evidence {item.supporting_evidence_ids.join(", ")}</small></div></article>) : <p className="quiet">No hypothesis cleared deterministic validation.</p>}<div className="validation-list">{validations.map((item) => <span key={item.validation_id} className={item.status === "PASS" ? "pass" : "muted"}>{human(item.kind)} · {item.status}</span>)}</div></section>; }
function ConfidencePanel({ report }: { report: Report }) { return <section className="confidence-card"><h3>Confidence controls</h3><dl><div><dt>Band</dt><dd>{report.confidence.band}</dd></div><div><dt>Completeness</dt><dd>{report.completeness.status}</dd></div><div><dt>Coverage</dt><dd>{human(report.coverage_status)}</dd></div></dl><h4>Positive factors</h4><ul>{report.confidence.positive_factors.map((item) => <li key={item}>{item}</li>)}{report.confidence.positive_factors.length === 0 && <li>None recorded</li>}</ul><h4>Caps</h4><ul>{report.confidence.applied_caps.map((item) => <li key={item}>{human(item)}</li>)}{report.confidence.applied_caps.length === 0 && <li>No caps applied</li>}</ul></section>; }
function Metric({ label, value, emphasis = false }: { label: string; value: string; emphasis?: boolean }) { return <div className="metric"><span>{label}</span><strong className={emphasis ? "positive" : ""}>{value}</strong></div>; }

const missingExternalGates: ReleaseGate[] = [
  { name: "External development gold", status: "NOT_RUN", detail: "External corpus not attached to this checkout." },
  { name: "Sealed holdout", status: "NOT_RUN", detail: "Sealed labels and reports are kept outside the product runtime." },
  { name: "Credentialed Live smoke", status: "NOT_RUN", detail: "Provider and model credentials are not configured here." },
];

function AssertionPanel({ assertions, evidenceIds, onInspect }: { assertions: Assertion[]; evidenceIds: Set<string>; onInspect: (assertion: Assertion) => void }) { return <section className="decision-card"><div className="section-title"><div><h3>Evidence assertions</h3><p>Only exact, hash-bound spans can support a published causal claim.</p></div><span>{assertions.length} item{assertions.length === 1 ? "" : "s"}</span></div>{assertions.length ? <div className="decision-list">{assertions.map((item) => <article key={item.assertion_id}><div><b>{item.assertion_id} · {item.evidence_id}</b><p>Exact source text is retained in the controlled passage viewer.</p><small>{human(item.mechanism_hint)} · {item.causal_eligible ? "Causal input" : "Not causal"} · {item.locator ?? "Locator unavailable"}</small><code>span {item.span_hash} · artifact {item.artifact_hash}</code></div>{evidenceIds.has(item.evidence_id) && <button className="text-button" onClick={() => onInspect(item)}>Open exact passage</button>}</article>)}</div> : <p className="quiet">No time-eligible assertions were registered.</p>}</section>; }
function MechanismPanel({ tests }: { tests: MechanismTest[] }) { return <section className="decision-card"><div className="section-title"><div><h3>Mechanism tests</h3><p>Deterministic checks test each causal mechanism against registered assertions.</p></div></div>{tests.length ? <div className="decision-list">{tests.map((item) => <article key={item.test_id}><div><b>{human(item.mechanism)} · {item.status}</b><p>{item.summary}</p><small>Support: {item.supporting_assertion_ids.join(", ") || "none"} · Contradiction: {item.contradicting_assertion_ids.join(", ") || "none"}</small><code>{item.policy_version}</code></div></article>)}</div> : <p className="quiet">No mechanism test was recorded.</p>}</section>; }
function LedgerPanel({ entries }: { entries: LedgerEntry[] }) { return <section className="decision-card"><div className="section-title"><div><h3>Decision ledger</h3><p>Append-only stage metadata and artifact hashes. No raw provider response or model reasoning is shown.</p></div></div>{entries.length ? <div className="decision-list">{entries.map((item) => <article key={item.sequence}><div><b>{item.sequence}. {human(item.stage)} · {item.status}</b><small>{item.schema_version ?? "ledger-v1"} · {item.policy_version} · {new Date(item.created_at).toLocaleString("en-AU", { timeZone: "Australia/Sydney", dateStyle: "medium", timeStyle: "short" })}</small><code>in {item.input_hashes.join(", ") || "none"}</code><code>out {item.output_hashes.join(", ") || "none"}</code></div></article>)}</div> : <p className="quiet">No decision ledger was recorded.</p>}</section>; }
function CalibrationPanel({ metadata, gates }: { metadata: CalibrationMetadata; gates: ReleaseGate[] }) { const bands = Object.entries(metadata.bands); return <section className="decision-card"><div className="section-title"><div><h3>Calibration sample status</h3><p>Confidence remains an ordinal evidence-strength band. Counts are not probability estimates.</p></div><span>{human(metadata.status)}</span></div><div className="calibration-list"><p><b>{metadata.label}</b><small>{metadata.corpus_version ?? "No reviewed development artifact attached"} · {metadata.confidence_rule_version ?? "Rule version unavailable"}</small></p>{bands.map(([band, sample]) => <p key={band}><b>{band}</b><small>{human(sample.status)} · {sample.eligible_cases} eligible cases · {sample.material_errors} material errors</small></p>)}{bands.length === 0 && <p className="quiet">No reviewed calibration samples are attached to this case.</p>}</div><h4>Release gates</h4><div className="gate-list">{gates.map((gate) => <p key={gate.name}><b>{gate.name}</b><span className={gate.status === "PASS" ? "gate-pass" : gate.status === "FAIL" ? "gate-fail" : "gate-not-run"}>{human(gate.status)}</span><small>{gate.detail}</small></p>)}</div></section>; }
