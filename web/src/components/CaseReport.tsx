import { useEffect, useRef, useState } from "react";
import {
  ChartLineUp,
  CheckCircle,
  DownloadSimple,
  FileText,
  WarningCircle,
  X,
} from "@phosphor-icons/react";

import { apiBase, loadVersionReport } from "../api";
import type {
  Assertion,
  CalibrationMetadata,
  Evidence,
  Hypothesis,
  LedgerEntry,
  MechanismTest,
  ReleaseGate,
  Report,
  RetrievalPlan,
  Validation,
} from "../types";

type ReportTab = "overview" | "evidence" | "audit";
const tabOrder: ReportTab[] = ["overview", "evidence", "audit"];

function human(value: string) {
  return value.replaceAll("_", " ").toLowerCase();
}

function title(value: string) {
  const text = human(value);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function statusLabel(value: string) {
  return value === "NOT_RUN" ? "NOT RUN" : title(value);
}

function percent(value?: number) {
  return value === undefined ? "-" : `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function aud(value?: number) {
  return value === undefined
    ? "-"
    : `AUD ${new Intl.NumberFormat("en-AU", { maximumFractionDigits: 0 }).format(value)}`;
}

function confidenceTone(band?: string) {
  return band === "HIGH" ? "high" : band === "MEDIUM" ? "medium" : "low";
}

function sydneyTime(value: string) {
  return new Date(value).toLocaleString("en-AU", {
    timeZone: "Australia/Sydney",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function ReportView({
  report,
  onRefined,
}: {
  report: Report;
  onRefined: (caseId: string) => void;
}) {
  const [selected, setSelected] = useState<Evidence | null>(null);
  const [passage, setPassage] = useState<{
    passage: string;
    locator?: string;
    page?: number;
  } | null>(null);
  const [parentReport, setParentReport] = useState<Report | null>(null);
  const [activeTab, setActiveTab] = useState<ReportTab>("overview");
  const primary = report.claims.find(
    (claim) => claim.claim_id === report.assessment.primary_claim_id,
  );

  useEffect(() => {
    if (!report.parent_version_id) {
      setParentReport(null);
      return;
    }
    void loadVersionReport(report.case_id, report.parent_version_id)
      .then(setParentReport)
      .catch(() => setParentReport(null));
  }, [report.case_id, report.parent_version_id]);

  async function inspect(item: Evidence) {
    setSelected(item);
    setPassage(null);
    const response = await fetch(`${apiBase}${item.content_endpoint}`);
    if (response.ok) setPassage(await response.json());
  }

  function inspectAssertion(assertion: Assertion) {
    const evidence = report.evidence.find(
      (item) => item.evidence_id === assertion.evidence_id,
    );
    if (evidence) void inspect(evidence);
  }

  async function refine(options: {
    primary_only?: boolean;
    excluded_evidence_ids?: string[];
  }) {
    const response = await fetch(
      `${apiBase}/api/v1/investigations/${report.case_id}/versions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(options),
      },
    );
    if (response.ok) {
      onRefined(((await response.json()) as { case_id: string }).case_id);
    }
  }

  function moveTab(current: ReportTab, direction: number) {
    const index = tabOrder.indexOf(current);
    const next = tabOrder[(index + direction + tabOrder.length) % tabOrder.length];
    setActiveTab(next);
    document.getElementById(`case-tab-${next}`)?.focus();
  }

  return (
    <div className="report-stack">
      <section className="report-head">
        <div>
          <p className="eyebrow">CASE RESULT / VERSION {report.case_version}</p>
          <h2>
            {report.instrument.company_name} <span>({report.ticker})</span>
          </h2>
          <p>
            {report.trade_date} / {report.timezone_label} /{" "}
            {report.instrument.sector ?? "ASX-listed equity"}
          </p>
          <div className="outcome-line">
            <span>{title(report.outcome)}</span>
            <span>{title(report.status)}</span>
          </div>
        </div>
        <div className={`confidence ${confidenceTone(report.confidence.band)}`}>
          <span>Selected hypothesis</span>
          <strong>{report.confidence.band}</strong>
          <small>
            {report.confidence.calibration_status} / {report.confidence.rule_version}
          </small>
        </div>
      </section>

      <div className="report-toolbar">
        <div className="report-tabs" role="tablist" aria-label="Case review sections">
          {tabOrder.map((tab) => (
            <button
              id={`case-tab-${tab}`}
              key={tab}
              type="button"
              role="tab"
              aria-selected={activeTab === tab}
              aria-controls={`case-panel-${tab}`}
              tabIndex={activeTab === tab ? 0 : -1}
              onClick={() => setActiveTab(tab)}
              onKeyDown={(event) => {
                if (event.key === "ArrowRight") moveTab(tab, 1);
                if (event.key === "ArrowLeft") moveTab(tab, -1);
              }}
            >
              {title(tab)}
            </button>
          ))}
        </div>
        <div className="report-actions">
          <a href={`${apiBase}/api/v1/investigations/${report.case_id}?format=markdown`}>
            <DownloadSimple size={15} /> Export Markdown
          </a>
          <button onClick={() => void refine({ primary_only: true })}>
            <FileText size={15} /> Primary sources only
          </button>
        </div>
      </div>

      <section
        id="case-panel-overview"
        role="tabpanel"
        aria-labelledby="case-tab-overview"
        hidden={activeTab !== "overview"}
        className="tab-panel"
      >
        <section className="metric-grid">
          <Metric
            label="Close-to-close"
            value={percent(report.market_move?.close_return_pct)}
            emphasis
          />
          <Metric label="Opening gap" value={percent(report.market_move?.open_gap_pct)} />
          <Metric
            label="Open to close"
            value={percent(report.market_move?.open_to_close_pct)}
          />
          <Metric label="Turnover" value={aud(report.market_move?.turnover_aud)} />
          <Metric
            label="Market relative"
            value={percent(report.market_move?.market_relative_return_pct ?? undefined)}
          />
        </section>
        <section className="assessment-card">
          <div className="section-kicker">
            <ChartLineUp size={18} /> Leading assessment
          </div>
          <h3>{report.assessment.summary}</h3>
          <div className="assessment-footer">
            <span className="chip">{primary?.claim_type ?? "UNRESOLVED"}</span>
            <span>Coverage: {title(report.coverage_status)}</span>
            <span>Completeness: {title(report.completeness.status)}</span>
            {report.confidence.applied_caps.map((cap) => (
              <span className="caution" key={cap}>
                {title(cap)}
              </span>
            ))}
          </div>
        </section>
        <InvestigationPlanView plan={report.retrieval_plan ?? null} />
        <section className="analysis-grid">
          <Hypotheses items={report.hypotheses} validations={report.validation_results} />
          <ConfidencePanel report={report} />
        </section>
        <CoverageAndConflicts report={report} />
      </section>

      <section
        id="case-panel-evidence"
        role="tabpanel"
        aria-labelledby="case-tab-evidence"
        hidden={activeTab !== "evidence"}
        className="tab-panel"
      >
        <EvidenceRegister evidence={report.evidence} onInspect={inspect} />
        <section className="decision-grid" aria-label="Audited evidence decisions">
          <AssertionPanel
            assertions={report.assertions}
            onInspect={inspectAssertion}
            evidenceIds={new Set(report.evidence.map((item) => item.evidence_id))}
          />
          <MechanismPanel tests={report.mechanism_tests} />
        </section>
      </section>

      <section
        id="case-panel-audit"
        role="tabpanel"
        aria-labelledby="case-tab-audit"
        hidden={activeTab !== "audit"}
        className="tab-panel"
      >
        {parentReport && <VersionComparison current={report} parent={parentReport} />}
        <section className="decision-grid" aria-label="Audited case records">
          <LedgerPanel entries={report.ledger} />
          <CalibrationPanel
            metadata={report.calibration_metadata}
            gates={report.release_gates ?? missingExternalGates}
          />
        </section>
        <section id="method" className="method-note">
          <CheckCircle size={18} />
          <p>
            Confidence is a rule-governed evidence-strength band, not a probability.
            Completeness and claim support are assessed separately.
          </p>
        </section>
      </section>

      {selected && (
        <EvidenceDrawer
          evidence={selected}
          passage={passage}
          onClose={() => setSelected(null)}
          onExclude={() =>
            void refine({ excluded_evidence_ids: [selected.evidence_id] })
          }
        />
      )}
    </div>
  );
}

function InvestigationPlanView({ plan }: { plan: RetrievalPlan | null }) {
  return (
    <section className="plan-card">
      <div className="section-title">
        <div>
          <h3>Investigation plan</h3>
          <p>Seven bounded driver lanes run under deterministic source policy.</p>
        </div>
        <span>{plan ? plan.policy_version : "Legacy case"}</span>
      </div>
      {plan ? (
        <div className="lane-list">
          {plan.lanes.map((lane) => (
            <article key={lane.lane}>
              <div>
                <b>{title(lane.lane)}</b>
                <small>
                  {lane.source_count} source{lane.source_count === 1 ? "" : "s"}
                  {lane.evidence_ids.length > 0
                    ? ` / Evidence ${lane.evidence_ids.join(", ")}`
                    : ""}
                </small>
              </div>
              <span className={`lane-status lane-${lane.status.toLowerCase()}`}>
                {title(lane.status)}
              </span>
              {lane.reason_code && <em>{title(lane.reason_code)}</em>}
            </article>
          ))}
          <footer>
            <span>Plan SHA-256 {plan.plan_hash}</span>
            <span>Evidence-gap follow-up {plan.follow_up_used ? "used" : "not used"}</span>
          </footer>
        </div>
      ) : (
        <p className="quiet">
          This persisted case predates the public retrieval-plan contract.
        </p>
      )}
    </section>
  );
}

function EvidenceDrawer({
  evidence,
  passage,
  onClose,
  onExclude,
}: {
  evidence: Evidence;
  passage: { passage: string; locator?: string; page?: number } | null;
  onClose: () => void;
  onExclude: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);
  return (
    <div className="passage-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="passage-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="passage-title"
        onClick={(event) => event.stopPropagation()}
      >
        <button
          ref={closeRef}
          className="drawer-close"
          onClick={onClose}
          aria-label="Close passage"
        >
          <X size={18} />
        </button>
        <span className="chip">{evidence.evidence_id}</span>
        <h3 id="passage-title">{evidence.title}</h3>
        <p className="drawer-meta">
          {title(evidence.authority)} / {passage?.locator ?? evidence.locator ?? "No locator"}
        </p>
        <blockquote>
          {passage?.passage ?? "Exact passage unavailable for this case version."}
        </blockquote>
        <div className="drawer-actions">
          <button onClick={onExclude}>Exclude in child version</button>
        </div>
      </aside>
    </div>
  );
}

export function VersionComparison({ current, parent }: { current: Report; parent: Report }) {
  return (
    <section className="comparison-bar" aria-label="Version comparison">
      <b>Compared with v{parent.case_version}</b>
      <span>
        {title(parent.outcome)} to {title(current.outcome)}
      </span>
      <span>
        {parent.confidence.band} to {current.confidence.band}
      </span>
      <span>
        {parent.evidence.length} to {current.evidence.length} evidence items
      </span>
      <p>
        <strong>Parent decision artifacts</strong> / {parent.assessment.summary}
      </p>
      <small>
        Assertions {parent.assertions.map((item) => item.assertion_id).join(", ") || "none"}
        {" / "}Mechanisms{" "}
        {parent.mechanism_tests
          .map((item) => `${title(item.mechanism)} ${item.status}`)
          .join(", ") || "none"}
      </small>
    </section>
  );
}

function Hypotheses({
  items,
  validations,
}: {
  items: Hypothesis[];
  validations: Validation[];
}) {
  return (
    <section className="hypothesis-card">
      <h3>Ranked hypotheses</h3>
      {items.length ? (
        items.map((item) => (
          <article key={item.hypothesis_id}>
            <span>{item.rank}</span>
            <div>
              <b>{title(item.driver_label)}</b>
              <p>{item.statement}</p>
              <small>
                {title(item.status)} / Evidence {item.supporting_evidence_ids.join(", ")}
              </small>
            </div>
          </article>
        ))
      ) : (
        <p className="quiet">No hypothesis cleared deterministic validation.</p>
      )}
      <div className="validation-list">
        {validations.map((item) => (
          <span
            key={item.validation_id}
            className={item.status === "PASS" ? "pass" : "muted"}
          >
            {title(item.kind)} / {item.status}
          </span>
        ))}
      </div>
    </section>
  );
}

function ConfidencePanel({ report }: { report: Report }) {
  return (
    <section className="confidence-card">
      <h3>Confidence controls</h3>
      <dl>
        <div>
          <dt>Band</dt>
          <dd>{report.confidence.band}</dd>
        </div>
        <div>
          <dt>Completeness</dt>
          <dd>{report.completeness.status}</dd>
        </div>
        <div>
          <dt>Coverage</dt>
          <dd>{title(report.coverage_status)}</dd>
        </div>
      </dl>
      <h4>Positive factors</h4>
      <ul>
        {report.confidence.positive_factors.map((item) => (
          <li key={item}>{item}</li>
        ))}
        {report.confidence.positive_factors.length === 0 && <li>None recorded</li>}
      </ul>
      <h4>Caps</h4>
      <ul>
        {report.confidence.applied_caps.map((item) => (
          <li key={item}>{title(item)}</li>
        ))}
        {report.confidence.applied_caps.length === 0 && <li>No caps applied</li>}
      </ul>
    </section>
  );
}

function Metric({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong className={emphasis ? "positive" : ""}>{value}</strong>
    </div>
  );
}

function CoverageAndConflicts({ report }: { report: Report }) {
  if (report.coverage_gaps.length === 0 && report.conflicts.length === 0) return null;
  return (
    <section className="exceptions-card">
      <h3>Coverage and conflicts</h3>
      <div className="exception-grid">
        {report.coverage_gaps.map((gap) => (
          <article key={gap.gap_id}>
            <WarningCircle size={18} />
            <div>
              <b>{title(gap.capability)}</b>
              <p>Coverage is incomplete for this capability.</p>
              <small>
                {gap.retryable
                  ? "Retry may be available."
                  : "No retry is available for this recorded gap."}
              </small>
            </div>
          </article>
        ))}
        {report.conflicts.map((conflict) => (
          <article key={conflict.conflict_id}>
            <WarningCircle size={18} />
            <div>
              <b>{title(conflict.field)} conflict</b>
              <p>
                {conflict.primary_source} {conflict.primary_value} /{" "}
                {conflict.secondary_source} {conflict.secondary_value}
              </p>
              <small>{conflict.resolution}</small>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function EvidenceRegister({
  evidence,
  onInspect,
}: {
  evidence: Evidence[];
  onInspect: (item: Evidence) => void;
}) {
  return (
    <section className="evidence-card">
      <div className="section-title">
        <div>
          <h3>Evidence register</h3>
          <p>Open an item to inspect the exact stored passage and locator.</p>
        </div>
        <span>
          {evidence.length} item{evidence.length === 1 ? "" : "s"}
        </span>
      </div>
      {evidence.length ? (
        <div className="evidence-list">
          {evidence.map((item) => (
            <button
              className="evidence-item"
              key={item.evidence_id}
              onClick={() => onInspect(item)}
            >
              <span className="evidence-number">
                {item.evidence_id.split(":").at(-1)}
              </span>
              <span>
                <span className="evidence-meta">
                  <em>{title(item.authority)}</em>
                  <em>{sydneyTime(item.published_at)}</em>
                  <em>{title(item.role)}</em>
                </span>
                <b>{item.title}</b>
                <p>Exact source text is available through the controlled passage viewer.</p>
                <small>
                  {item.source_host ?? item.source_name} / {item.locator ?? "Locator unavailable"}
                </small>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="no-evidence">No time-eligible evidence was registered.</p>
      )}
    </section>
  );
}

const missingExternalGates: ReleaseGate[] = [
  {
    name: "External development gold",
    status: "NOT_RUN",
    detail: "External corpus not attached to this checkout.",
  },
  {
    name: "Sealed holdout",
    status: "NOT_RUN",
    detail: "Sealed labels and reports are kept outside the product runtime.",
  },
  {
    name: "Credentialed Live smoke",
    status: "NOT_RUN",
    detail: "Provider and model credentials are not configured here.",
  },
];

function AssertionPanel({
  assertions,
  evidenceIds,
  onInspect,
}: {
  assertions: Assertion[];
  evidenceIds: Set<string>;
  onInspect: (assertion: Assertion) => void;
}) {
  return (
    <section className="decision-card">
      <div className="section-title">
        <div>
          <h3>Evidence assertions</h3>
          <p>Only exact, hash-bound spans can support a published causal claim.</p>
        </div>
        <span>
          {assertions.length} item{assertions.length === 1 ? "" : "s"}
        </span>
      </div>
      {assertions.length ? (
        <div className="decision-list">
          {assertions.map((item) => (
            <article key={item.assertion_id}>
              <div>
                <b>
                  {item.assertion_id} / {item.evidence_id}
                </b>
                <p>Exact source text is retained in the controlled passage viewer.</p>
                <small>
                  {title(item.mechanism_hint)} /{" "}
                  {item.causal_eligible ? "Causal input" : "Not causal"} /{" "}
                  {item.locator ?? "Locator unavailable"}
                </small>
                <code>
                  span {item.span_hash} / artifact {item.artifact_hash}
                </code>
              </div>
              {evidenceIds.has(item.evidence_id) && (
                <button className="text-button" onClick={() => onInspect(item)}>
                  Open exact passage
                </button>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p className="quiet">No time-eligible assertions were registered.</p>
      )}
    </section>
  );
}

function MechanismPanel({ tests }: { tests: MechanismTest[] }) {
  return (
    <section className="decision-card">
      <div className="section-title">
        <div>
          <h3>Mechanism tests</h3>
          <p>Deterministic checks test each mechanism against registered assertions.</p>
        </div>
      </div>
      {tests.length ? (
        <div className="decision-list">
          {tests.map((item) => (
            <article key={item.test_id}>
              <div>
                <b>
                  {title(item.mechanism)} / {item.status}
                </b>
                <p>{item.summary}</p>
                <small>
                  Support: {item.supporting_assertion_ids.join(", ") || "none"} /{" "}
                  Contradiction: {item.contradicting_assertion_ids.join(", ") || "none"}
                </small>
                <code>{item.policy_version}</code>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="quiet">No mechanism test was recorded.</p>
      )}
    </section>
  );
}

function LedgerPanel({ entries }: { entries: LedgerEntry[] }) {
  return (
    <section className="decision-card">
      <div className="section-title">
        <div>
          <h3>Decision ledger</h3>
          <p>Append-only stages and artifact hashes. Private model reasoning is excluded.</p>
        </div>
      </div>
      {entries.length ? (
        <div className="decision-list">
          {entries.map((item) => (
            <article key={item.sequence}>
              <div>
                <b>
                  {item.sequence}. {title(item.stage)} / {item.status}
                </b>
                <small>
                  {item.schema_version ?? "ledger-v1"} / {item.policy_version} /{" "}
                  {sydneyTime(item.created_at)}
                </small>
                <code>in {item.input_hashes.join(", ") || "none"}</code>
                <code>out {item.output_hashes.join(", ") || "none"}</code>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="quiet">No decision ledger was recorded.</p>
      )}
    </section>
  );
}

function CalibrationPanel({
  metadata,
  gates,
}: {
  metadata: CalibrationMetadata;
  gates: ReleaseGate[];
}) {
  const bands = Object.entries(metadata.bands);
  return (
    <section className="decision-card">
      <div className="section-title">
        <div>
          <h3>Calibration sample status</h3>
          <p>Confidence remains ordinal. Counts are not probability estimates.</p>
        </div>
        <span>{statusLabel(metadata.status)}</span>
      </div>
      <div className="calibration-list">
        <p>
          <b>{metadata.label}</b>
          <small>
            {metadata.corpus_version ?? "No reviewed development artifact attached"} /{" "}
            {metadata.confidence_rule_version ?? "Rule version unavailable"}
          </small>
        </p>
        {bands.map(([band, sample]) => (
          <p key={band}>
            <b>{band}</b>
            <small>
              {title(sample.status)} / {sample.eligible_cases} eligible cases /{" "}
              {sample.material_errors} material errors
            </small>
          </p>
        ))}
        {bands.length === 0 && (
          <p className="quiet">No reviewed calibration samples are attached to this case.</p>
        )}
      </div>
      <h4>Release gates</h4>
      <div className="gate-list">
        {gates.map((gate) => (
          <p key={gate.name}>
            <b>{gate.name}</b>
            <span
              className={
                gate.status === "PASS"
                  ? "gate-pass"
                  : gate.status === "FAIL"
                    ? "gate-fail"
                    : "gate-not-run"
              }
            >
              {statusLabel(gate.status)}
            </span>
            <small>{gate.detail}</small>
          </p>
        ))}
      </div>
    </section>
  );
}
