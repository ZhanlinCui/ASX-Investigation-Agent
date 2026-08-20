import { FormEvent, useEffect, useState } from "react";
import {
  ArrowSquareOut,
  BookOpenText,
  CaretRight,
  ChartLineUp,
  CheckCircle,
  ClipboardText,
  Clock,
  FileText,
  MagnifyingGlass,
  ShieldCheck,
  Sparkle,
  WarningCircle,
} from "@phosphor-icons/react";

type Status = "IDLE" | "QUEUED" | "RUNNING" | "COMPLETED" | "PARTIAL" | "FAILED_RECOVERABLE";

type Evidence = {
  evidence_id: string;
  source_name: string;
  source_url: string;
  published_at: string;
  authority: string;
  title: string;
  passage: string;
  role: string;
  locator?: string;
};

type Report = {
  status: Status;
  ticker: string;
  trade_date: string;
  timezone_label: string;
  instrument: { company_name: string; sector?: string };
  market_move?: {
    close_return_pct: number;
    open_gap_pct: number;
    open_to_close_pct: number;
    turnover_aud: number;
    volume_zscore?: number;
    market_relative_return_pct?: number;
  };
  assessment: { primary_claim_id?: string; summary: string };
  claims: Array<{ claim_id: string; claim_type: string; text: string; confidence?: number }>;
  evidence: Evidence[];
  confidence: {
    score: number;
    band: string;
    calibration_status: string;
    applied_caps: string[];
  };
  coverage_status: string;
};

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

function percent(value: number | undefined) {
  return value === undefined ? "—" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function aud(value: number | undefined) {
  return value === undefined
    ? "—"
    : new Intl.NumberFormat("en-AU", { maximumFractionDigits: 0 }).format(value);
}

function confidenceTone(band?: string) {
  return band === "HIGH" ? "high" : band === "MEDIUM" ? "medium" : "low";
}

export default function App() {
  const [ticker, setTicker] = useState("BHP");
  const [tradeDate, setTradeDate] = useState("2026-08-20");
  const [mode, setMode] = useState("RECORDED");
  const [status, setStatus] = useState<Status>("IDLE");
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);

  useEffect(() => {
    if (!caseId || status === "COMPLETED" || status === "PARTIAL" || status === "FAILED_RECOVERABLE") {
      return;
    }
    const stream = new EventSource(`${apiBase}/api/v1/investigations/${caseId}/events`);
    stream.onmessage = () => undefined;
    stream.addEventListener("status", (event) => {
      setStatus(JSON.parse(event.data).status as Status);
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
      if (["COMPLETED", "PARTIAL"].includes(payload.status)) setReport(payload);
      if (payload.status === "FAILED_RECOVERABLE") setError(payload.error ?? "Investigation failed.");
    }, 550);
    return () => window.clearInterval(timer);
  }, [caseId, status]);

  async function investigate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setReport(null);
    setStatus("QUEUED");
    try {
      const response = await fetch(`${apiBase}/api/v1/investigations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ticker, trade_date: tradeDate, mode }),
      });
      if (!response.ok) throw new Error("Check the ASX code and date, then try again.");
      const payload = (await response.json()) as { case_id: string };
      setCaseId(payload.case_id);
    } catch (caught) {
      setStatus("FAILED_RECOVERABLE");
      setError(caught instanceof Error ? caught.message : "Could not start investigation.");
    }
  }

  const active = status === "QUEUED" || status === "RUNNING";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">A</span><span>ASX Investigator</span></div>
        <nav aria-label="Primary">
          <a className="nav-item active" href="#investigate"><MagnifyingGlass size={18} /> Investigate</a>
          <a className="nav-item" href="#cases"><ClipboardText size={18} /> Case archive</a>
          <a className="nav-item" href="#method"><BookOpenText size={18} /> Method</a>
        </nav>
        <div className="sidebar-foot">
          <div className="source-status"><span className="status-dot" /> Evidence-first analysis</div>
          <p>Each material claim must cite its source and timing.</p>
        </div>
      </aside>

      <main id="investigate" className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">MARKET INVESTIGATION</p><h1>Investigate a market move</h1></div>
          <div className="calendar-note"><Clock size={16} /> All values AUD · ASX trading calendar</div>
        </header>

        <section className="case-form-card" aria-label="New investigation">
          <form onSubmit={investigate}>
            <label className="field-label" htmlFor="ticker">ASX code</label>
            <div className="search-row">
              <div className="input-with-icon"><MagnifyingGlass size={18} /><input id="ticker" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="e.g. BHP" maxLength={6} /></div>
              <div className="date-field"><label className="field-label" htmlFor="date">Trading date</label><input id="date" type="date" value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} /></div>
              <select aria-label="Data mode" value={mode} onChange={(e) => setMode(e.target.value)}><option value="LIVE">Live sources</option><option value="RECORDED">Recorded case</option></select>
              <button className="primary-button" type="submit" disabled={active}>{active ? "Investigating…" : "Investigate"}<CaretRight size={16} weight="bold" /></button>
            </div>
          </form>
          <div className="case-hints"><span><ShieldCheck size={16} /> Evidence timing is checked against AEST/AEDT session boundaries.</span><span><FileText size={16} /> Recorded mode is available for regression and demos.</span></div>
        </section>

        {active && <section className="working-card"><div className="pulse" /><div><strong>{status === "QUEUED" ? "Preparing case" : "Reviewing market data and evidence"}</strong><p>Calculating the price signature, then screening source timing and claim support.</p></div></section>}
        {error && <section className="error-card"><WarningCircle size={20} /><div><strong>Investigation unavailable</strong><p>{error}</p></div></section>}
        {!report && !active && !error && <EmptyState onRecorded={() => { setTicker("BHP"); setTradeDate("2026-08-20"); setMode("RECORDED"); }} />}
        {report && <ReportView report={report} />}
      </main>
    </div>
  );
}

function EmptyState({ onRecorded }: { onRecorded: () => void }) {
  return <section className="empty-state"><div className="empty-icon"><Sparkle size={24} /></div><h2>Start with the trading session</h2><p>Enter an ASX-listed equity and a trading date. The agent separates observed market facts from evidence-backed explanations.</p><div className="suggestions"><button onClick={onRecorded}>Open the recorded BHP case <CaretRight size={15} /></button><span>Live cases require configured market-data sources.</span></div></section>;
}

function ReportView({ report }: { report: Report }) {
  const primary = report.claims.find((claim) => claim.claim_id === report.assessment.primary_claim_id);
  return <div className="report-stack">
    <section className="report-head"><div><p className="eyebrow">CASE RESULT</p><h2>{report.instrument.company_name} <span>({report.ticker})</span></h2><p>{report.trade_date} · {report.timezone_label} · {report.instrument.sector ?? "ASX-listed equity"}</p></div><div className={`confidence ${confidenceTone(report.confidence.band)}`}><span>Confidence</span><strong>{report.confidence.band}</strong><small>{Math.round(report.confidence.score * 100)}% · {report.confidence.calibration_status}</small></div></section>
    <section className="metric-grid">
      <Metric label="Close-to-close" value={percent(report.market_move?.close_return_pct)} emphasis />
      <Metric label="Opening gap" value={percent(report.market_move?.open_gap_pct)} />
      <Metric label="Open to close" value={percent(report.market_move?.open_to_close_pct)} />
      <Metric label="Turnover" value={`A$${aud(report.market_move?.turnover_aud)}`} />
      <Metric label="Market relative" value={percent(report.market_move?.market_relative_return_pct)} />
    </section>
    <section className="assessment-card"><div className="section-kicker"><ChartLineUp size={18} /> Leading assessment</div><h3>{report.assessment.summary}</h3><div className="assessment-footer"><span className="chip">{primary?.claim_type ?? "UNRESOLVED"}</span><span>Coverage: {report.coverage_status.replaceAll("_", " ")}</span>{report.confidence.applied_caps.map((cap) => <span className="caution" key={cap}>{cap.replaceAll("_", " ")}</span>)}</div></section>
    <section className="evidence-card"><div className="section-title"><div><p className="eyebrow">EVIDENCE REGISTER</p><h3>Sources behind this assessment</h3></div><span>{report.evidence.length} item{report.evidence.length === 1 ? "" : "s"}</span></div>{report.evidence.length ? <div className="evidence-list">{report.evidence.map((item) => <article className="evidence-item" key={item.evidence_id}><div className="evidence-number">{item.evidence_id}</div><div><div className="evidence-meta"><span>{item.authority.replaceAll("_", " ")}</span><span>{new Date(item.published_at).toLocaleString("en-AU", { timeZone: "Australia/Sydney", dateStyle: "medium", timeStyle: "short" })}</span></div><h4>{item.title}</h4><p>{item.passage}</p><a href={item.source_url} target="_blank" rel="noreferrer">Open source <ArrowSquareOut size={14} /></a></div></article>)}</div> : <p className="no-evidence">No source is sufficiently time-eligible to support a causal claim.</p>}</section>
    <section className="method-note"><CheckCircle size={18} /><p>Confidence is provisional until calibration against held-out cases is completed. It is capped when primary evidence or disclosure coverage is incomplete.</p></section>
  </div>;
}

function Metric({ label, value, emphasis = false }: { label: string; value: string; emphasis?: boolean }) {
  return <div className="metric"><span>{label}</span><strong className={emphasis ? "positive" : ""}>{value}</strong></div>;
}
