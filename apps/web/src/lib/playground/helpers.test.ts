import { describe, expect, it } from "vitest";

import { displayValue, profileDiff } from "./helpers";

describe("playground helpers", () => {
  it("shows missing values without turning them into zero", () => {
    expect(displayValue(null)).toBe("—");
    expect(displayValue(1200)).toBe("1200");
  });

  it("returns only changed profile fields", () => {
    expect(profileDiff({ budget_max: 1200, zones: ["palermo"] }, { budget_max: 1000, zones: ["palermo"] })).toEqual([
      { key: "budget_max", before: 1200, after: 1000 },
    ]);
  });
});

