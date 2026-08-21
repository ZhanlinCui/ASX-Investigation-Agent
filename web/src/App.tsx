import { type FormEvent, useEffect, useState } from "react";
import {
  ArrowClockwise,
  BookOpenText,
  ClipboardText,
  Clock,
  MagnifyingGlass,
  WarningCircle,
} from "@phosphor-icons/react";

import { apiBase } from "./api";
import { ReportView } from "./components/CaseReport";
import { InvestigationForm } from "./components/InvestigationForm";
import { EmptyState, RunningTimeline } from "./components/InvestigationStates";
import { toSydneyIso } from "./time";
import type { ArchiveItem, Report, Stage, Status } from "./types";

function title(value: string) {
  const text = value.replaceAll("_", " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

async function fetchArchive(): Promise<ArchiveItem[] | null> {
  try {
    const response = await fetch(`${apiBase}/api/v1/investigations`);
    return response.ok
      ? ((await response.json()) as { items: ArchiveItem[] }).items
      : null;
  } catch {
    return null;
  }
}

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

  useEffect(() => {
    let current = true;
    void fetchArchive().then((items) => {
      if (current && items) setArchive(items);
    });
    return () => {
      current = false;
    };
  }, []);

  useEffect(() => {
    if (!caseId) return;
    const stream = new EventSource(
      `${apiBase}/api/v1/investigations/${caseId}/events`,
    );
    stream.addEventListener("status", (event) =>
      setStatus(JSON.parse(event.data).status as Status),
    );
    stream.addEventListener("stage", (event) => {
      const item = JSON.parse(event.data) as Stage;
      setStages((current) => [
        ...current.filter(
          (value) => !(value.stage === item.stage && value.status === item.status),
        ),
        item,
      ]);
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
      if (payload.status === "COMPLETED") {
        setReport(payload);
        void fetchArchive().then((items) => {
          if (items) setArchive(items);
        });
      }
      if (payload.status === "FAILED_RECOVERABLE") {
        setError(payload.error ?? "Investigation failed at a recoverable stage.");
      }
    }, 450);
    return () => window.clearInterval(timer);
  }, [caseId, status]);

  async function investigate(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setReport(null);
    setStages([]);
    setStatus("QUEUED");
    try {
      const response = await fetch(`${apiBase}/api/v1/investigations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker,
          trade_date: tradeDate,
          mode,
          source_ids: sourceIds,
        }),
      });
      if (!response.ok) {
        throw new Error("Check the ASX code, session date, and configured sources.");
      }
      setCaseId(((await response.json()) as { case_id: string }).case_id);
    } catch (caught) {
      setStatus("FAILED_RECOVERABLE");
      setError(
        caught instanceof Error ? caught.message : "Could not start investigation.",
      );
    }
  }

  async function openCase(item: ArchiveItem) {
    const response = await fetch(`${apiBase}/api/v1/investigations/${item.case_id}`);
    if (!response.ok) return;
    const payload = (await response.json()) as Report & { error?: string };
    setCaseId(item.case_id);
    setStatus(payload.status);
    setError(payload.error ?? null);
    setStages([]);
    setReport(payload.status === "COMPLETED" ? payload : null);
  }

  async function uploadSource(file?: File) {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("title", file.name);
      body.append("published_at", toSydneyIso(sourcePublishedAt));
      body.append("is_official", "false");
      const response = await fetch(`${apiBase}/api/v1/sources/upload`, {
        method: "POST",
        body,
      });
      if (response.ok) {
        const source = (await response.json()) as { source_id: string };
        setSourceIds((current) => [...current, source.source_id]);
      } else {
        setError("The source could not be frozen. Use PDF or text up to 20 MB.");
      }
    } catch {
      setError("The source could not be frozen because the API is unavailable.");
    } finally {
      setUploading(false);
    }
  }

  async function retry() {
    if (!caseId) return;
    const response = await fetch(
      `${apiBase}/api/v1/investigations/${caseId}/retry`,
      { method: "POST" },
    );
    if (response.ok) {
      setError(null);
      setStatus("QUEUED");
    }
  }

  const active = status === "QUEUED" || status === "RUNNING";
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">A</span>
          <span>ASX Investigator</span>
        </div>
        <nav aria-label="Primary">
          <a className="nav-item active" href="#investigate">
            <MagnifyingGlass size={18} /> Investigate
          </a>
          <a className="nav-item" href="#cases">
            <ClipboardText size={18} /> Case archive
          </a>
          <a className="nav-item" href="#method">
            <BookOpenText size={18} /> Method
          </a>
        </nav>
        <div id="cases" className="archive-list">
          <span>Recent cases</span>
          {archive.slice(0, 8).map((item) => (
            <button key={item.version_id} onClick={() => void openCase(item)}>
              <b>{item.ticker}</b>
              <small>
                {item.trade_date} / v{item.version_number}
              </small>
              <em>{title(item.outcome ?? item.status)}</em>
            </button>
          ))}
        </div>
        <div className="sidebar-foot">
          <div className="source-status">Evidence-first analysis</div>
          <p>Claims, source timing, provider gaps, and conflicts remain auditable.</p>
        </div>
      </aside>

      <main id="investigate" className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">MARKET INVESTIGATION</p>
            <h1>Investigate a market move</h1>
          </div>
          <div className="calendar-note">
            <Clock size={16} /> All values AUD · ASX trading calendar
          </div>
        </header>
        <InvestigationForm
          ticker={ticker}
          tradeDate={tradeDate}
          mode={mode}
          active={active}
          uploading={uploading}
          sourcePublishedAt={sourcePublishedAt}
          sourceCount={sourceIds.length}
          onSubmit={investigate}
          onTickerChange={setTicker}
          onDateChange={(value) => {
            setTradeDate(value);
            setSourcePublishedAt(`${value}T08:00`);
          }}
          onModeChange={setMode}
          onPublishedAtChange={setSourcePublishedAt}
          onUpload={(file) => void uploadSource(file)}
        />

        {active && <RunningTimeline status={status} stages={stages} />}
        {error && (
          <section className="error-card">
            <WarningCircle size={20} />
            <div>
              <strong>Investigation unavailable</strong>
              <p>{error}</p>
              {caseId && status === "FAILED_RECOVERABLE" && (
                <button className="text-button" onClick={() => void retry()}>
                  <ArrowClockwise size={15} /> Retry
                </button>
              )}
            </div>
          </section>
        )}
        {!report && !active && !error && (
          <EmptyState
            onRecorded={() => {
              setTicker("BHP");
              setTradeDate("2026-08-20");
              setMode("RECORDED");
            }}
          />
        )}
        {report && (
          <ReportView
            report={report}
            onRefined={(id) => {
              setCaseId(id);
              setReport(null);
              setStatus("QUEUED");
              setStages([]);
            }}
          />
        )}
      </main>
    </div>
  );
}
