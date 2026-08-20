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
type Evidence = { evidence_id: string; source_name: string; source_url: string; published_at: string; authority: string; title: string; passage: string; role: string; locator?: string; page?: number };
type Hypothesis = { hypothesis_id: string; rank: number; status: string; driver_label: string; statement: string; expected_signature?: string; supporting_evidence_ids: string[]; contradicting_evidence_ids: string[] };
type Validation = { validation_id: string; kind: string; status: string; summary: string };
type Gap = { gap_id: string; capability: string; provider: string; reason: string; impact: string };
type Conflict = { conflict_id: string; field: string; primary_source: string; primary_value: string; secondary_source: string; secondary_value: string; resolution: string };

type Report = {
  case_id: string; run_id: string; case_version: number; parent_version_id?: string; status: Status; outcome: string;
  ticker: string; trade_date: string; timezone_label: string;
  instrument: { company_name: string; sector?: string };
  market_move?: { close_return_pct: number; open_gap_pct: number; open_to_close_pct: number; turnover_aud: number; volume_zscore?: number; market_relative_return_pct?: number };
  assessment: { primary_claim_id?: string; summary: string };
  claims: Array<{ claim_id: string; claim_type: string; text: string }>;
  evidence: Evidence[]; hypotheses: Hypothesis[]; validation_results: Validation[]; coverage_gaps: Gap[]; conflicts: Conflict[];
  confidence: { band: string; calibration_status: string; positive_factors: string[]; negative_factors: string[]; applied_caps: string[]; rule_version: string };
  completeness: { status: string; required_capabilities: string[]; missing_capabilities: string[] };
  coverage_status: string; source_policy_version: string; model_configuration: Record<string, string>;
  trace: Array<{ node: string; status: string }>;
};

type ArchiveItem = { case_id: string; version_id: string; version_number: number; ticker: string; trade_date: string; status: string; outcome?: string; report_payload?: Report };

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
    if (!caseId || terminalStatuses.includes(status)) return;
    const stream = new EventSource(`${apiBase}/api/v1/investigations/${caseId}/events`);
    stream.addEventListener("status", (event) => setStatus(JSON.parse(event.data).status as Status));
    stream.addEventListener("stage", (event) => {
      const item = JSON.parse(event.data) as Stage;
      setStages((current) => [...current.filter((value) => !(value.stage === item.stage && value.status === item.status)), item]);
    });
    stream.addEventListener("completed", () => stream.close());
    stream.addEventListener("failed", () => stream.close());
    return () => stream.close();
  }, [caseId, status]);

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
    const payload = (await response.json()) as Report;
    setCaseId(item.case_id); setStatus(payload.status); setReport(payload); setError(null); setStages([]);
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
      {error && <section className="error-card"><WarningCircle size={20} /><div><strong>Investigation unavailable</strong><p>{error}</p>{caseId && <button className="text-button" onClick={() => void fetch(`${apiBase}/api/v1/investigations/${caseId}/retry`, { method: "POST" }).then(() => setStatus("QUEUED"))}><ArrowClockwise size={15} /> Retry</button>}</div></section>}
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
  return <section className="empty-state"><div className="empty-icon"><Sparkle size={24} /></div><h2>Start with the trading session</h2><p>Observed facts stay separate from evidence-backed explanations. Missing coverage produces an abstention, not a guess.</p><div className="suggestions"><button onClick={onRecorded}>Load the recorded BHP case <CaretRight size={15} /></button><span>Live cases require configured provider credentials.</span></div></section>;
}

function ReportView({ report, onRefined }: { report: Report; onRefined: (caseId: string) => void }) {
  const [selected, setSelected] = useState<Evidence | null>(null);
  const [passage, setPassage] = useState<{ passage: string; locator?: string; page?: number } | null>(null);
  const [versions, setVersions] = useState<ArchiveItem[]>([]);
  const primary = report.claims.find((claim) => claim.claim_id === report.assessment.primary_claim_id);
  useEffect(() => { void fetch(`${apiBase}/api/v1/investigations/${report.case_id}/versions`).then((response) => response.json()).then((payload: { items: ArchiveItem[] }) => setVersions(payload.items)); }, [report.case_id]);
  async function inspect(item: Evidence) { setSelected(item); setPassage(null); const response = await fetch(`${apiBase}/api/v1/evidence/${encodeURIComponent(item.evidence_id)}/content`); setPassage(response.ok ? await response.json() : { passage: item.passage, locator: item.locator, page: item.page }); }
  async function refine() { const response = await fetch(`${apiBase}/api/v1/investigations/${report.case_id}/versions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ primary_only: true, excluded_evidence_ids: [] }) }); if (response.ok) onRefined(((await response.json()) as { case_id: string }).case_id); }
  const parent = versions.find((item) => item.version_id === report.parent_version_id)?.report_payload;
  return <div className="report-stack">
    <section className="report-head"><div><p className="eyebrow">CASE RESULT · VERSION {report.case_version}</p><h2>{report.instrument.company_name} <span>({report.ticker})</span></h2><p>{report.trade_date} · {report.timezone_label} · {report.instrument.sector ?? "ASX-listed equity"}</p><div className="outcome-line"><span>{human(report.outcome)}</span><span>{human(report.status)}</span></div></div><div className={`confidence ${confidenceTone(report.confidence.band)}`}><span>Selected hypothesis</span><strong>{report.confidence.band}</strong><small>{report.confidence.calibration_status} · {report.confidence.rule_version}</small></div></section>
    <div className="report-actions"><a href={`${apiBase}/api/v1/investigations/${report.case_id}?format=markdown`}><DownloadSimple size={15} /> Export Markdown</a><button onClick={() => void refine()}><FileText size={15} /> Refine as child version</button></div>
    {parent && <section className="comparison-bar"><b>Compared with v{parent.case_version}</b><span>{human(parent.outcome)} → {human(report.outcome)}</span><span>{parent.confidence.band} → {report.confidence.band}</span></section>}
    <section className="metric-grid"><Metric label="Close-to-close" value={percent(report.market_move?.close_return_pct)} emphasis /><Metric label="Opening gap" value={percent(report.market_move?.open_gap_pct)} /><Metric label="Open to close" value={percent(report.market_move?.open_to_close_pct)} /><Metric label="Turnover" value={aud(report.market_move?.turnover_aud)} /><Metric label="Market relative" value={percent(report.market_move?.market_relative_return_pct)} /></section>
    <section className="assessment-card"><div className="section-kicker"><ChartLineUp size={18} /> Leading assessment</div><h3>{report.assessment.summary}</h3><div className="assessment-footer"><span className="chip">{primary?.claim_type ?? "UNRESOLVED"}</span><span>Coverage: {human(report.coverage_status)}</span><span>Completeness: {human(report.completeness.status)}</span>{report.confidence.applied_caps.map((cap) => <span className="caution" key={cap}>{human(cap)}</span>)}</div></section>
    <section className="analysis-grid"><Hypotheses items={report.hypotheses} validations={report.validation_results} /><ConfidencePanel report={report} /></section>
    {(report.coverage_gaps.length > 0 || report.conflicts.length > 0) && <section className="exceptions-card"><h3>Coverage and conflicts</h3><div className="exception-grid">{report.coverage_gaps.map((gap) => <article key={gap.gap_id}><WarningCircle size={18} /><div><b>{human(gap.capability)}</b><p>{gap.reason}</p><small>{gap.impact}</small></div></article>)}{report.conflicts.map((conflict) => <article key={conflict.conflict_id}><WarningCircle size={18} /><div><b>{human(conflict.field)} conflict</b><p>{conflict.primary_source} {conflict.primary_value} · {conflict.secondary_source} {conflict.secondary_value}</p><small>{conflict.resolution}</small></div></article>)}</div></section>}
    <section className="evidence-card"><div className="section-title"><div><h3>Evidence register</h3><p>Open an item to inspect the exact stored passage and locator.</p></div><span>{report.evidence.length} item{report.evidence.length === 1 ? "" : "s"}</span></div>{report.evidence.length ? <div className="evidence-list">{report.evidence.map((item) => <button className="evidence-item" key={item.evidence_id} onClick={() => void inspect(item)}><span className="evidence-number">{item.evidence_id.split(":").at(-1)}</span><span><span className="evidence-meta"><em>{human(item.authority)}</em><em>{new Date(item.published_at).toLocaleString("en-AU", { timeZone: "Australia/Sydney", dateStyle: "medium", timeStyle: "short" })}</em><em>{human(item.role)}</em></span><b>{item.title}</b><p>{item.passage}</p><small>{item.locator ?? "Locator unavailable"}</small></span></button>)}</div> : <p className="no-evidence">No time-eligible evidence was registered.</p>}</section>
    <details className="trace-card"><summary>Investigation trace and configuration</summary><div><p>Source policy {report.source_policy_version} · Model {report.model_configuration.model ?? report.model_configuration.provider ?? "deterministic"}</p>{report.trace.map((item, index) => <span key={`${item.node}-${index}`}>{human(item.node)} <b>{item.status}</b></span>)}</div></details>
    <section id="method" className="method-note"><CheckCircle size={18} /><p>Confidence is a rule-governed evidence-strength band, not a probability. Completeness and claim support are assessed separately.</p></section>
    {selected && <div className="passage-backdrop" role="presentation" onClick={() => setSelected(null)}><aside className="passage-drawer" role="dialog" aria-modal="true" aria-label="Evidence passage" onClick={(event) => event.stopPropagation()}><button className="drawer-close" onClick={() => setSelected(null)} aria-label="Close passage"><X size={18} /></button><span className="chip">{selected.evidence_id}</span><h3>{selected.title}</h3><p className="drawer-meta">{human(selected.authority)} · {passage?.locator ?? selected.locator ?? "No locator"}</p><blockquote>{passage?.passage ?? "Loading exact passage…"}</blockquote>{selected.source_url.startsWith("http") && <a href={selected.source_url} target="_blank" rel="noreferrer">Open original source</a>}</aside></div>}
  </div>;
}

function Hypotheses({ items, validations }: { items: Hypothesis[]; validations: Validation[] }) { return <section className="hypothesis-card"><h3>Ranked hypotheses</h3>{items.length ? items.map((item) => <article key={item.hypothesis_id}><span>{item.rank}</span><div><b>{human(item.driver_label)}</b><p>{item.statement}</p><small>{human(item.status)} · Evidence {item.supporting_evidence_ids.join(", ")}</small></div></article>) : <p className="quiet">No hypothesis cleared deterministic validation.</p>}<div className="validation-list">{validations.map((item) => <span key={item.validation_id} className={item.status === "PASS" ? "pass" : "muted"}>{human(item.kind)} · {item.status}</span>)}</div></section>; }
function ConfidencePanel({ report }: { report: Report }) { return <section className="confidence-card"><h3>Confidence controls</h3><dl><div><dt>Band</dt><dd>{report.confidence.band}</dd></div><div><dt>Completeness</dt><dd>{report.completeness.status}</dd></div><div><dt>Coverage</dt><dd>{human(report.coverage_status)}</dd></div></dl><h4>Positive factors</h4><ul>{report.confidence.positive_factors.map((item) => <li key={item}>{item}</li>)}{report.confidence.positive_factors.length === 0 && <li>None recorded</li>}</ul><h4>Caps</h4><ul>{report.confidence.applied_caps.map((item) => <li key={item}>{human(item)}</li>)}{report.confidence.applied_caps.length === 0 && <li>No caps applied</li>}</ul></section>; }
function Metric({ label, value, emphasis = false }: { label: string; value: string; emphasis?: boolean }) { return <div className="metric"><span>{label}</span><strong className={emphasis ? "positive" : ""}>{value}</strong></div>; }
