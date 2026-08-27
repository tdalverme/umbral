import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(resolve(process.cwd(), path), "utf8");

describe("brand foundations", () => {
  it("declares the approved Luz serena palette", () => {
    const css = read("src/app/globals.css").toUpperCase();
    expect(css).toContain("--BRAND-FOREST: #293F38");
    expect(css).toContain("--BRAND-LINEN: #F4EFE6");
    expect(css).toContain("--BRAND-TERRACOTTA: #DE6D4A");
    expect(css).toContain("--BRAND-SAND: #D9C59F");
    expect(css).toContain("--BRAND-IVORY: #FFFAF2");
  });

  it("loads and exposes DM Sans and Fraunces through next/font", () => {
    const layout = read("src/app/layout.tsx");
    expect(layout).toContain('from "next/font/google"');
    expect(layout).toContain('variable: "--font-sans"');
    expect(layout).toContain('variable: "--font-brand"');
  });
});
