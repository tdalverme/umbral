# Umbral Visual Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce the final “Umbral abierto” SVG logo suite and install Umbral's approved color and typography foundations in the Next.js application without redesigning product screens.

**Architecture:** Brand assets live as immutable SVG files under `apps/web/public/brand`, while reusable presentation enters React through one focused `BrandLogo` component. Font loading stays in the App Router root layout through `next/font/google`; shadcn semantic tokens remain the only colors consumed by UI primitives, with named brand tokens added to `globals.css` as the source values.

**Tech Stack:** SVG 1.1, Next.js App Router, React 19, TypeScript 6, Tailwind CSS 4, shadcn/ui semantic tokens, Vitest, Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-26-umbral-brand-system-design.md`

## Global Constraints

- Brand name: **Umbral**.
- Primary line: **“Tu próximo lugar se acerca.”**
- Visual direction: **Luz serena**.
- Logo principle: **Umbral abierto**, with a small terracotta opportunity accent.
- Brand colors: forest `#293F38`, linen `#F4EFE6`, terracotta `#DE6D4A`, sand `#D9C59F`, ivory `#FFFAF2`.
- Display type: **Fraunces Semibold**. Interface and body type: **DM Sans Regular/Medium/Semibold**.
- The symbol must work in monochrome and remain recognizable at 16 px.
- Do not use a literal house, magnifying glass, location pin, robot, or generic radar.
- Terracotta signals opportunity or novelty; it must not be the destructive/error color.
- shadcn components consume semantic classes such as `bg-primary` and `text-muted-foreground`; no raw brand colors in component class names.
- Every text/background combination introduced by this increment must meet WCAG 2.2 AA.
- Do not redesign product pages, chat, cards, navigation, or marketing surfaces in this increment.

---

### Task 1: Refine and select the “Umbral abierto” symbol

**Files:**
- Create: `docs/brand/logo/concepts/umbral-open-balanced.svg`
- Create: `docs/brand/logo/concepts/umbral-open-soft.svg`
- Create: `docs/brand/logo/concepts/umbral-open-threshold.svg`
- Create: `docs/brand/logo/concepts/README.md`

**Interfaces:**
- Consumes: the approved arch/opening metaphor, forest and terracotta colors from the brand spec.
- Produces: one user-selected geometry identified as `balanced`, `soft`, or `threshold`; Task 2 uses that exact geometry for every final asset.

- [ ] **Step 1: Create three bounded SVG refinements**

Use a `64 64` viewBox for all concepts, no filters, no gradients, and no embedded font. Each file must contain a unique `<title>` and `<desc>`.

`balanced` uses a circular arch with a straight baseline and a centered opportunity accent:

```xml
<path d="M14 52V30C14 18.954 22.954 10 34 10s20 8.954 20 20v22" fill="none" stroke="#293F38" stroke-width="6" stroke-linecap="round"/>
<path d="M29 52h10" fill="none" stroke="#DE6D4A" stroke-width="6" stroke-linecap="round"/>
```

`soft` uses a wider, lower arch to feel calmer and more domestic:

```xml
<path d="M10 52V34c0-13.255 10.745-24 24-24s24 10.745 24 24v18" fill="none" stroke="#293F38" stroke-width="6" stroke-linecap="round"/>
<path d="M29 52h10" fill="none" stroke="#DE6D4A" stroke-width="6" stroke-linecap="round"/>
```

`threshold` makes the opening and floor relationship more explicit without drawing a house:

```xml
<path d="M14 52V30C14 18.954 22.954 10 34 10s20 8.954 20 20v22" fill="none" stroke="#293F38" stroke-width="6" stroke-linecap="round"/>
<path d="M8 52h18m16 0h16" fill="none" stroke="#293F38" stroke-width="6" stroke-linecap="round"/>
<path d="M29 52h10" fill="none" stroke="#DE6D4A" stroke-width="6" stroke-linecap="round"/>
```

- [ ] **Step 2: Document the comparison criteria**

In `README.md`, record the same five checks for each concept:

```markdown
1. Recognition at 16 px and 24 px.
2. Clear opening/transition metaphor without reading as a house.
3. Stable silhouette in one color.
4. Optical balance beside the word “umbral”.
5. No collision or disappearance on linen, ivory, and forest backgrounds.
```

- [ ] **Step 3: Verify that every SVG is well-formed**

Run:

```powershell
Get-ChildItem docs\brand\logo\concepts\*.svg | ForEach-Object { [xml](Get-Content -Raw $_.FullName) | Out-Null }
```

Expected: command exits with code 0 and no parser errors.

- [ ] **Step 4: Present the three SVGs at 16, 24, 64, and 192 px**

Open a local comparison using the in-app browser. Show each concept on linen, ivory, and forest plus one monochrome rendering. Ask the user to choose exactly one geometry before Task 2. Do not infer the winner from this plan.

- [ ] **Step 5: Record the selected geometry**

Add the section below to `README.md` after explicit user feedback. Use exactly
one of the three complete approval sentences and delete the other two:

```markdown
## Selected geometry

`balanced` was approved on 2026-08-26. All production variants derive from this geometry; the other files remain concept records and are not shipped by the web app.

`soft` was approved on 2026-08-26. All production variants derive from this geometry; the other files remain concept records and are not shipped by the web app.

`threshold` was approved on 2026-08-26. All production variants derive from this geometry; the other files remain concept records and are not shipped by the web app.
```

- [ ] **Step 6: Commit the concept checkpoint**

```powershell
git add docs/brand/logo/concepts
git commit -m "design: refine Umbral open symbol"
```

### Task 2: Build and test the production SVG logo suite

**Files:**
- Create: `apps/web/public/brand/umbral-symbol-color.svg`
- Create: `apps/web/public/brand/umbral-symbol-dark.svg`
- Create: `apps/web/public/brand/umbral-symbol-light.svg`
- Create: `apps/web/public/brand/umbral-logo-horizontal-color.svg`
- Create: `apps/web/public/brand/umbral-logo-horizontal-dark.svg`
- Create: `apps/web/public/brand/umbral-logo-horizontal-light.svg`
- Create: `apps/web/public/brand/umbral-favicon.svg`
- Create: `apps/web/src/components/brand/logo-assets.test.ts`

**Interfaces:**
- Consumes: the selected path geometry from Task 1.
- Produces: stable public URLs under `/brand/*`; Task 4's `BrandLogo` maps component variants to these URLs.

- [ ] **Step 1: Write a failing asset contract test**

Create `logo-assets.test.ts` with an explicit manifest and assert each file's structure:

```ts
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm --workspace @umbral/web run test -- src/components/brand/logo-assets.test.ts`

Expected: FAIL because `public/brand` does not exist.

- [ ] **Step 3: Create the symbol variants from one geometry**

Use the selected Task 1 path without coordinate changes:

- `color`: forest arch plus terracotta accent.
- `dark`: all paths `#293F38`.
- `light`: all paths `#FFFAF2`.
- `favicon`: color geometry on a linen rounded-square field with at least 6 viewBox units of breathing room.

Every root must include `xmlns`, `viewBox`, `role="img"`, `aria-labelledby`, `<title>Logo de Umbral</title>`, and a concise Spanish `<desc>`.

- [ ] **Step 4: Create horizontal lockups**

Use a `0 0 280 64` viewBox, place the selected symbol at `0 0 64 64`, and add `umbral` as the wordmark at x `80`. Use a `<text>` element with:

```xml
font-family="Fraunces, Georgia, serif" font-size="46" font-weight="600" letter-spacing="-1.4"
```

Color mappings:

- `horizontal-color`: forest wordmark, color symbol.
- `horizontal-dark`: forest wordmark and symbol.
- `horizontal-light`: ivory wordmark and symbol.

- [ ] **Step 5: Run the asset contract**

Run: `npm --workspace @umbral/web run test -- src/components/brand/logo-assets.test.ts`

Expected: PASS for all seven assets.

- [ ] **Step 6: Check SVG parsing and repository size**

Run:

```powershell
Get-ChildItem apps\web\public\brand\*.svg | ForEach-Object { [xml](Get-Content -Raw $_.FullName) | Out-Null }
Get-ChildItem apps\web\public\brand\*.svg | Measure-Object -Property Length -Sum
```

Expected: no XML errors and total size below 40 KB.

- [ ] **Step 7: Commit the production logo suite**

```powershell
git add apps/web/public/brand apps/web/src/components/brand/logo-assets.test.ts
git commit -m "feat(web): add Umbral logo assets"
```

### Task 3: Install brand typography and semantic color tokens

**Files:**
- Modify: `apps/web/src/app/layout.tsx`
- Modify: `apps/web/src/app/globals.css`
- Create: `apps/web/src/app/brand-foundations.test.ts`

**Interfaces:**
- Consumes: Fraunces and DM Sans through `next/font/google`; exact palette values from the spec.
- Produces: CSS variables `--font-brand`, `--font-sans`, `--brand-forest`, `--brand-linen`, `--brand-terracotta`, `--brand-sand`, and `--brand-ivory`; existing shadcn semantic variables remain the UI interface.

- [ ] **Step 1: Write failing source-contract tests**

Read `globals.css` and `layout.tsx` as text. Assert the five exact hex values, both font variables, and the `next/font/google` imports:

```ts
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
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `npm --workspace @umbral/web run test -- src/app/brand-foundations.test.ts`

Expected: FAIL because the brand variables and font configuration are absent.

- [ ] **Step 3: Configure fonts at module scope**

In `layout.tsx`, add:

```ts
import { DM_Sans, Fraunces } from "next/font/google";

const dmSans = DM_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const fraunces = Fraunces({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-brand",
});
```

Apply `className={`${dmSans.variable} ${fraunces.variable}`}` to `<html>` so font metadata is static and loaded once.

- [ ] **Step 4: Define brand source tokens and map light semantic tokens**

At the start of `:root`, declare the exact five brand variables. Map light mode as follows:

```css
--background: var(--brand-linen);
--foreground: var(--brand-forest);
--card: var(--brand-ivory);
--card-foreground: var(--brand-forest);
--popover: var(--brand-ivory);
--popover-foreground: var(--brand-forest);
--primary: var(--brand-forest);
--primary-foreground: var(--brand-ivory);
--secondary: color-mix(in srgb, var(--brand-sand) 42%, var(--brand-ivory));
--secondary-foreground: var(--brand-forest);
--accent: color-mix(in srgb, var(--brand-terracotta) 18%, var(--brand-ivory));
--accent-foreground: var(--brand-forest);
```

Keep `--destructive` independent from terracotta. Derive muted, border, input, and ring from forest/linen/sand with `color-mix`. Preserve a usable dark theme by mapping dark semantic tokens rather than adding `dark:` utility overrides.

- [ ] **Step 5: Expose font utilities through Tailwind and body**

In `@theme inline`, add:

```css
--font-sans: var(--font-sans);
--font-brand: var(--font-brand);
```

Change the body family to `var(--font-sans), Arial, Helvetica, sans-serif`. Do not apply Fraunces globally.

- [ ] **Step 6: Run focused and primitive tests**

Run:

```powershell
npm --workspace @umbral/web run test -- src/app/brand-foundations.test.ts src/components/ui/foundation.test.tsx
```

Expected: both files PASS; primitive tests still find semantic color classes.

- [ ] **Step 7: Run typecheck**

Run: `npm --workspace @umbral/web run typecheck`

Expected: PASS with valid `next/font` configuration.

- [ ] **Step 8: Commit typography and tokens**

```powershell
git add apps/web/src/app/layout.tsx apps/web/src/app/globals.css apps/web/src/app/brand-foundations.test.ts
git commit -m "feat(web): install Umbral visual tokens"
```

### Task 4: Add the reusable BrandLogo component

**Files:**
- Create: `apps/web/src/components/brand/brand-logo.tsx`
- Create: `apps/web/src/components/brand/brand-logo.test.tsx`

**Interfaces:**
- Consumes: `/brand/umbral-logo-horizontal-{color,dark,light}.svg` and `/brand/umbral-symbol-{color,dark,light}.svg` from Task 2.
- Produces: `BrandLogo({ layout, tone, className, priority }): ReactElement`, where `layout` is `"horizontal" | "symbol"` and `tone` is `"color" | "dark" | "light"`.

- [ ] **Step 1: Write the failing component tests**

```tsx
import { render, screen } from "@testing-library/react";

import { BrandLogo } from "./brand-logo";

describe("BrandLogo", () => {
  it("renders the horizontal color logo with an accessible name", () => {
    render(<BrandLogo />);
    expect(screen.getByRole("img", { name: "Umbral" })).toHaveAttribute(
      "src",
      expect.stringContaining("/brand/umbral-logo-horizontal-color.svg"),
    );
  });

  it("supports a light symbol for compact dark surfaces", () => {
    render(<BrandLogo layout="symbol" tone="light" />);
    expect(screen.getByRole("img", { name: "Umbral" })).toHaveAttribute(
      "src",
      expect.stringContaining("/brand/umbral-symbol-light.svg"),
    );
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm --workspace @umbral/web run test -- src/components/brand/brand-logo.test.tsx`

Expected: FAIL because `BrandLogo` does not exist.

- [ ] **Step 3: Implement the minimal server-compatible component**

Use `next/image`, a static lookup object, width/height `280/64` for horizontal and `64/64` for symbol, and no client directive. The component must set `alt="Umbral"`, accept `className`, and choose `priority` only when the caller opts in. Do not inline the SVG or accept arbitrary asset paths.

```tsx
type BrandLogoProps = {
  className?: string;
  layout?: "horizontal" | "symbol";
  priority?: boolean;
  tone?: "color" | "dark" | "light";
};
```

- [ ] **Step 4: Run component tests**

Run: `npm --workspace @umbral/web run test -- src/components/brand/brand-logo.test.tsx`

Expected: PASS.

- [ ] **Step 5: Commit the reusable component**

```powershell
git add apps/web/src/components/brand/brand-logo.tsx apps/web/src/components/brand/brand-logo.test.tsx
git commit -m "feat(web): add Umbral brand logo component"
```

### Task 5: Wire metadata, document usage, and visually verify foundations

**Files:**
- Modify: `apps/web/src/app/layout.tsx`
- Modify: `apps/web/src/app/page.test.tsx`
- Create: `docs/brand/visual-foundations.md`

**Interfaces:**
- Consumes: final favicon, logo URLs, font and color tokens from Tasks 2–4.
- Produces: production metadata and the usage contract for subsequent UI and marketing plans.

- [ ] **Step 1: Extend the failing metadata assertion**

In `page.test.tsx`, assert the exported metadata directly:

```ts
import RootLayout, { metadata } from "./layout";

expect(metadata).toMatchObject({
  title: "Umbral",
  description: "Tu próximo lugar se acerca.",
  icons: { icon: "/brand/umbral-favicon.svg" },
});
```

- [ ] **Step 2: Run the page test to verify it fails**

Run: `npm --workspace @umbral/web run test -- src/app/page.test.tsx`

Expected: FAIL because description and icon still describe the runtime foundation.

- [ ] **Step 3: Update root metadata**

Set:

```ts
export const metadata: Metadata = {
  title: "Umbral",
  description: "Tu próximo lugar se acerca.",
  icons: { icon: "/brand/umbral-favicon.svg" },
};
```

- [ ] **Step 4: Write the operational visual-foundations guide**

Document:

- asset inventory and which variant to use on linen, ivory, forest, and photography;
- logo clear space equal to one quarter of the symbol width;
- minimum sizes: 16 px symbol, 100 px horizontal digital, 25 mm horizontal print;
- color table with exact hex values and semantic roles;
- Fraunces restricted to brand headings and DM Sans for UI/body;
- prohibited distortion, rotation, shadows, recoloring, busy backgrounds, literal-house additions, and use of terracotta as an error color;
- example React usage for every `BrandLogo` layout/tone;
- export commands using a detected local renderer; if neither Inkscape nor ImageMagick exists, document the missing local PNG-export tool instead of adding a dependency.

- [ ] **Step 5: Run the complete web verification**

Run:

```powershell
npm --workspace @umbral/web run test
npm --workspace @umbral/web run typecheck
npm --workspace @umbral/web run lint
npm --workspace @umbral/web run build
```

Expected: all commands PASS. If a pre-existing failure is reproduced, record its exact command and output; do not weaken the new tests.

- [ ] **Step 6: Inspect responsive and theme states in the browser**

Run the development app and inspect at 320 px, 768 px, and 1440 px in light and dark modes. Verify:

- no font loading layout break;
- primary buttons and focus rings remain visible;
- cards remain distinguishable from backgrounds;
- text contrast is readable;
- favicon loads;
- each logo variant stays sharp at its minimum size.

Use automated accessibility inspection on the root page and one protected product surface. Expected: zero serious or critical color-contrast violations introduced by this increment.

- [ ] **Step 7: Commit documentation and metadata**

```powershell
git add apps/web/src/app/layout.tsx apps/web/src/app/page.test.tsx docs/brand/visual-foundations.md
git commit -m "docs: publish Umbral visual foundations"
```

- [ ] **Step 8: Run the repository harness**

Run: `.\scripts\check.ps1`

Expected: PASS. If unrelated environment-dependent suites fail, retain the focused web evidence and document the gap with the exact failing suite.
