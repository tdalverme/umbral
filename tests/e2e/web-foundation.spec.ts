import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const runtimeVersionFields = [
  "surface",
  "release_id",
  "git_sha",
  "artifact_digest",
  "manifest_sha256",
  "contract_major",
  "database_revision",
  "built_at",
] as const;

async function expectFoundationPage(page: import("@playwright/test").Page) {
  await page.goto("/");
  await expect(page.getByRole("main")).toBeVisible();
}

test("web health and version expose the side-effect-free runtime identity", async ({
  request,
}) => {
  const health = await request.get("/health");
  expect(health.status()).toBe(200);
  expect(health.headers()["cache-control"]).toBe("no-store");
  expect(await health.json()).toEqual({ status: "alive" });

  const version = await request.get("/version");
  expect(version.status()).toBe(200);
  expect(version.headers()["cache-control"]).toBe("no-store");

  const payload = await version.json();
  expect(Object.keys(payload).sort()).toEqual([...runtimeVersionFields].sort());
  expect(payload).toMatchObject({ surface: "web", contract_major: 1 });
});

test("keyboard users can reveal the skip link and move focus to main content", async ({ page }) => {
  await expectFoundationPage(page);

  const skipLink = page.getByRole("link", { name: /saltar al contenido principal/i });
  const main = page.getByRole("main");

  await page.keyboard.press("Tab");
  await expect(skipLink).toBeFocused();
  await expect(skipLink).toBeVisible();

  await page.keyboard.press("Enter");
  await expect(main).toBeFocused();
});

test.describe("foundation page in light color scheme", () => {
  test.use({ colorScheme: "light" });

  test("has no WCAG A/AA or contrast violations", async ({ page }) => {
    await expectFoundationPage(page);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();

    expect(results.violations).toEqual([]);
  });
});

test.describe("foundation page in dark color scheme", () => {
  test.use({ colorScheme: "dark" });

  test("has no WCAG A/AA or contrast violations", async ({ page }) => {
    await expectFoundationPage(page);

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();

    expect(results.violations).toEqual([]);
  });
});

test("reflows without horizontal overflow at 320 CSS pixels", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 720 });
  await expectFoundationPage(page);

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
});

test("respects reduced motion without retaining smooth scrolling or active animations", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expectFoundationPage(page);

  const motion = await page.evaluate(() => ({
    activeAnimations: document
      .getAnimations()
      .filter((animation) => animation.playState === "running").length,
    scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
  }));

  expect(motion.scrollBehavior).toBe("auto");
  expect(motion.activeAnimations).toBe(0);
});
