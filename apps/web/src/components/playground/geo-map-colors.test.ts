import { describe, expect, it } from "vitest";

import { categoryColorEntries, categoryColorExpression } from "./geo-map-colors";

describe("categoryColorEntries", () => {
  it("assigns one deterministic color to each visible category", () => {
    expect(categoryColorEntries(["park", "cafe", "park", "school"])).toEqual([
      { category: "cafe", color: "#e05252" },
      { category: "park", color: "#e08a2e" },
      { category: "school", color: "#c7a72b" },
    ]);
  });
});

describe("categoryColorExpression", () => {
  it("builds a MapLibre match expression with a fallback color", () => {
    expect(categoryColorExpression(["park", "cafe"])).toEqual([
      "match",
      ["get", "category"],
      "cafe",
      "#e05252",
      "park",
      "#e08a2e",
      "#64748b",
    ]);
  });
});
