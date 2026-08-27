import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const assets = [
  "umbral-symbol-color.svg",
  "umbral-symbol-dark.svg",
  "umbral-symbol-light.svg",
  "umbral-logo-horizontal-color.svg",
  "umbral-logo-horizontal-dark.svg",
  "umbral-logo-horizontal-light.svg",
  "umbral-favicon.svg",
] as const;

describe("Umbral logo assets", () => {
  it.each(assets)("ships an accessible, scalable %s", (asset) => {
    const source = readFileSync(resolve(process.cwd(), "public", "brand", asset), "utf8");
    expect(source).toContain("viewBox=");
    expect(source).toContain("<title");
    expect(source).toContain("<desc");
    expect(source).not.toContain("<filter");
    expect(source).not.toContain("<image");
  });
});
