import { describe, expect, it } from "vitest";

import { isTerminalRunState } from "@/lib/radar/run-state";

describe("run state", () => {
  it("treats failed runs as terminal so polling can stop", () => {
    expect(isTerminalRunState("failed")).toBe(true);
  });

  it("keeps pending and running runs pollable", () => {
    expect(isTerminalRunState("pending")).toBe(false);
    expect(isTerminalRunState("running")).toBe(false);
  });
});
