import type { FormEvent } from "react";
import {
  CaretRight,
  FileArrowUp,
  MagnifyingGlass,
  ShieldCheck,
} from "@phosphor-icons/react";

type Props = {
  ticker: string;
  tradeDate: string;
  mode: string;
  active: boolean;
  uploading: boolean;
  sourcePublishedAt: string;
  sourceCount: number;
  onSubmit: (event: FormEvent) => void;
  onTickerChange: (value: string) => void;
  onDateChange: (value: string) => void;
  onModeChange: (value: string) => void;
  onPublishedAtChange: (value: string) => void;
  onUpload: (file?: File) => void;
};

export function InvestigationForm(props: Props) {
  return (
    <section className="case-form-card" aria-label="New investigation">
      <form onSubmit={props.onSubmit}>
        <label className="field-label" htmlFor="ticker">
          ASX code
        </label>
        <div className="search-row">
          <div className="input-with-icon">
            <MagnifyingGlass size={18} />
            <input
              id="ticker"
              value={props.ticker}
              onChange={(event) => props.onTickerChange(event.target.value.toUpperCase())}
              maxLength={6}
              autoComplete="off"
            />
          </div>
          <div className="date-field">
            <label className="field-label" htmlFor="date">
              Trading date
            </label>
            <input
              id="date"
              type="date"
              value={props.tradeDate}
              onChange={(event) => props.onDateChange(event.target.value)}
            />
          </div>
          <label className="mode-field">
            <span className="field-label">Data mode</span>
            <select
              aria-label="Data mode"
              value={props.mode}
              onChange={(event) => props.onModeChange(event.target.value)}
            >
              <option value="LIVE">Live sources</option>
              <option value="RECORDED">Recorded case</option>
            </select>
          </label>
          <button className="primary-button" type="submit" disabled={props.active}>
            {props.active ? "Investigating..." : "Investigate"}
            <CaretRight size={16} weight="bold" />
          </button>
        </div>
      </form>
      <div className="case-hints">
        <span>
          <ShieldCheck size={16} /> AEST/AEDT timing is validated.
        </span>
        <label className="source-time">
          Source published (Sydney)
          <input
            type="datetime-local"
            value={props.sourcePublishedAt}
            onChange={(event) => props.onPublishedAtChange(event.target.value)}
          />
        </label>
        <label className="upload-control">
          <FileArrowUp size={16} />
          {props.uploading ? "Freezing source..." : "Add PDF or text"}
          <input
            type="file"
            accept="application/pdf,text/plain,text/html"
            onChange={(event) => props.onUpload(event.target.files?.[0])}
          />
        </label>
        {props.sourceCount > 0 && (
          <span>
            {props.sourceCount} frozen source{props.sourceCount === 1 ? "" : "s"} attached
          </span>
        )}
      </div>
    </section>
  );
}
