import { CaretRight, CheckCircle, Sparkle } from "@phosphor-icons/react";

import type { Stage, Status } from "../types";

function human(value: string) {
  return value.replaceAll("_", " ").toLowerCase();
}

export function RunningTimeline({ status, stages }: { status: Status; stages: Stage[] }) {
  const latest = stages.filter((item) => item.status === "RUNNING").at(-1)?.stage;
  return (
    <section className="working-card" aria-live="polite">
      <div className="pulse" />
      <div>
        <strong>{status === "QUEUED" ? "Preparing case" : human(latest ?? "evidence investigation")}</strong>
        <p>Each completed stage is checkpointed for replay and recovery.</p>
        <div className="stage-strip">
          {stages
            .filter((item) => item.status === "COMPLETED")
            .slice(-5)
            .map((item) => (
              <span key={`${item.stage}-${item.sequence}`}>
                <CheckCircle size={13} /> {human(item.stage)}
              </span>
            ))}
        </div>
      </div>
    </section>
  );
}

export function EmptyState({ onRecorded }: { onRecorded: () => void }) {
  return (
    <section className="empty-state">
      <div className="empty-icon">
        <Sparkle size={24} />
      </div>
      <h2>Start with the trading session</h2>
      <p>
        Observed facts stay separate from evidence-backed explanations. Missing coverage
        produces an abstention, not a guess.
      </p>
      <div className="suggestions">
        <button onClick={onRecorded}>
          Load the recorded BHP case <CaretRight size={15} />
        </button>
        <span>
          Live cases require configured provider credentials. Frozen provenance includes
          Artifact SHA-256 values.
        </span>
      </div>
    </section>
  );
}
