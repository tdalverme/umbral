import { expect, test } from "@playwright/test";

test.describe("private-beta identity boundary", () => {
  test("login acknowledges without revealing cohort membership", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("unknown@example.test");
    await page.getByRole("button", { name: "Enviar enlace" }).click();
    await expect(page.getByText(/Si la direcci/)).toBeVisible();
  });

  test("capture GET redirects without confirming a session", async ({ page }) => {
    const response = await page.request.get(
      "/auth/capture?attempt_id=00000000-0000-0000-0000-000000000000&token_hash=invalid",
      { maxRedirects: 0 },
    );
    expect(response.status()).toBe(303);
    expect(response.headers()["location"]).toContain("/auth/confirm");
    expect(response.headers()["set-cookie"]).toContain("umbral_capture=");
  });
});
