import { describe, expect, it } from "vitest";

import { caveatCopy, unknownCopy } from "./criterion-labels";

describe("criterion explanation copy", () => {
  it("keeps missing-data copy neutral across detail surfaces", () => {
    expect(unknownCopy("vida_nocturna")).toBe("No puedo confirmar actividad nocturna todavía.");
    expect(caveatCopy("vida_nocturna", "unknown")).toBe(unknownCopy("vida_nocturna"));
    expect(unknownCopy("vida_nocturna")).not.toMatch(/aviso no lo informa/i);
  });
});
