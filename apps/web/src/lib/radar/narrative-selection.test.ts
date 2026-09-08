import { describe, expect, it } from "vitest";

import { shouldResetNarrative } from "./narrative-selection";

describe("shouldResetNarrative", () => {
  it("preserva el resultado al seleccionar la misma identidad", () => {
    expect(
      shouldResetNarrative(
        { listingId: "listing-1", runId: "run-1" },
        "listing-1",
        "run-1",
      ),
    ).toBe(false);
  });

  it("reinicia al cambiar listing o run", () => {
    expect(shouldResetNarrative(null, "listing-1", "run-1")).toBe(true);
    expect(
      shouldResetNarrative(
        { listingId: "listing-1", runId: "run-1" },
        "listing-2",
        "run-1",
      ),
    ).toBe(true);
    expect(
      shouldResetNarrative(
        { listingId: "listing-1", runId: "run-1" },
        "listing-1",
        "run-2",
      ),
    ).toBe(true);
  });
});
