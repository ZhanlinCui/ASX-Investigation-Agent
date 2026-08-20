import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import App from "./App";
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
});
