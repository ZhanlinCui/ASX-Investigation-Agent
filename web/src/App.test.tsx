import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders an English investigation workspace", () => {
    const html = renderToStaticMarkup(<App />);

    expect(html).toContain("ASX Investigator");
    expect(html).toContain("Investigate a market move");
    expect(html).toContain("All values AUD · ASX trading calendar");
  });
});
