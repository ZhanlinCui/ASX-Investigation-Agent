/** @vitest-environment jsdom */

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EvidenceDrawer } from "./CaseReport";
import type { Evidence } from "../types";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
  .IS_REACT_ACT_ENVIRONMENT = true;

const evidence: Evidence = {
  evidence_id: "E1",
  source_name: "Recorded issuer source",
  source_host: "example.test",
  published_at: "2026-08-20T08:30:00+10:00",
  retrieved_at: "2026-08-20T09:00:00+10:00",
  authority: "PRIMARY_ISSUER",
  title: "Issuer update",
  role: "CAUSAL_INPUT",
  content_hash: "f".repeat(64),
  locator: "page=1",
  page: 1,
  content_endpoint: "/api/v1/evidence/E1/content?version_id=V1",
};

describe("EvidenceDrawer focus boundary", () => {
  afterEach(() => {
    document.body.replaceChildren();
  });

  it("cycles focus inside the modal, closes with Escape, and restores the opener", () => {
    const opener = document.createElement("button");
    opener.textContent = "Open exact passage";
    const mount = document.createElement("div");
    document.body.append(opener, mount);
    opener.focus();

    const onClose = vi.fn();
    const root = createRoot(mount);
    act(() => {
      root.render(
        <EvidenceDrawer
          evidence={evidence}
          passage={{ passage: "Frozen source passage.", locator: "page=1" }}
          onClose={onClose}
          onExclude={() => undefined}
        />,
      );
    });

    const close = document.querySelector<HTMLButtonElement>(
      'button[aria-label="Close passage"]',
    );
    const exclude = [...document.querySelectorAll<HTMLButtonElement>("button")].find(
      (button) => button.textContent === "Exclude in child version",
    );
    expect(document.querySelector('[role="dialog"][aria-modal="true"]')).not.toBeNull();
    expect(close).not.toBeNull();
    expect(exclude).not.toBeUndefined();
    expect(document.activeElement).toBe(close);

    exclude!.focus();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    expect(document.activeElement).toBe(close);

    close!.focus();
    document.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true }),
    );
    expect(document.activeElement).toBe(exclude);

    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    expect(onClose).toHaveBeenCalledOnce();

    act(() => root.unmount());
    expect(document.activeElement).toBe(opener);
  });
});
