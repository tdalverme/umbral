import { expect, test } from "@playwright/test";

const validAttemptId = "00000000-0000-0000-0000-000000000001";
const validTokenHash = "a".repeat(43);

test.describe("private-beta identity boundary", () => {
  test("login acknowledges without revealing cohort membership", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").fill("unknown@example.test");
    await page.getByRole("button", { name: "Enviar enlace" }).click();
    await expect(page.getByText(/Si la direcci/)).toBeVisible();
  });

  test("capture GET redirects without confirming a session", async ({ page }) => {
    const response = await page.request.get(
      `/auth/capture?attempt_id=${validAttemptId}&token_hash=${validTokenHash}`,
      { maxRedirects: 0 },
    );
    expect(response.status()).toBe(303);
    expect(response.headers()["location"]).toContain("/auth/confirm");
    expect(response.headers()["set-cookie"]).toContain("umbral_capture=");
    expect(response.headers()["set-cookie"]).toMatch(/HttpOnly/);
    expect(response.headers()["set-cookie"]).toMatch(/SameSite=Strict/i);
    expect(response.headers()["set-cookie"]).toMatch(/Path=\/auth/);
    expect(response.headers()["set-cookie"]).not.toMatch(/umbral_local_session=/);
  });

  test("scanner GET stores a capture but does not consume it", async ({ page }) => {
    const response = await page.request.get(
      `/auth/capture?attempt_id=${validAttemptId}&token_hash=${validTokenHash}`,
      { maxRedirects: 0 },
    );
    expect(response.status()).toBe(303);
    await page.goto("/auth/confirm");
    await expect(page.getByRole("button", { name: "Continuar a Umbral" })).toBeVisible();
    expect(await page.context().cookies()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: "umbral_capture", httpOnly: true, path: "/auth" }),
      ]),
    );
  });

  test("explicit confirmation POST creates a secure session cookie", async ({ page }) => {
    await page.request.get(
      `/auth/capture?attempt_id=${validAttemptId}&token_hash=${validTokenHash}`,
      { maxRedirects: 0 },
    );
    const response = await page.request.post("/api/auth/confirmations", {
      data: { attemptId: validAttemptId, tokenHash: validTokenHash },
    });
    expect(response.status()).toBe(204);
    expect(await page.context().cookies()).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          name: "umbral_local_session",
          httpOnly: true,
          secure: true,
          sameSite: "Lax",
          path: "/",
        }),
      ]),
    );
  });

  test("logout forwards the session and expires the cookie", async ({ page }) => {
    await page.context().addCookies([
      {
        name: "umbral_local_session",
        value: "e2e-session",
        url: "http://127.0.0.1:3000",
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
    const response = await page.request.post("/api/auth/logout");
    expect(response.status()).toBe(204);
    expect(response.headers()["set-cookie"]).toMatch(/Max-Age=0/);
    expect(response.headers()["set-cookie"]).toMatch(/HttpOnly/);
  });

  test("expired capture has a recoverable request-new-link path", async ({ page }) => {
    await page.goto("/auth/confirm?error=expired");
    await expect(page.getByText(/El enlace ya no est/)).toBeVisible();
    await expect(page.getByRole("link", { name: "Solicitar un enlace nuevo" })).toHaveAttribute(
      "href",
      "/login",
    );
  });

  test("Mailpit captures a link that can be opened by the browser", async ({ page, request }) => {
    const recipient = `e2e-${Date.now()}@example.test`;
    const captureUrl = `http://127.0.0.1:3000/auth/capture?attempt_id=${validAttemptId}&token_hash=${validTokenHash}`;
    const sent = await request.post("http://127.0.0.1:8025/api/v1/send", {
      data: {
        From: { Email: "umbral@example.test" },
        To: [{ Email: recipient }],
        Subject: "Umbral magic link",
        Text: captureUrl,
      },
    });
    expect(sent.ok()).toBeTruthy();

    const messagesResponse = await request.get("http://127.0.0.1:8025/api/v1/messages");
    expect(messagesResponse.ok()).toBeTruthy();
    const messages = (await messagesResponse.json()) as {
      messages: Array<{ ID: string; To: Array<{ Address: string }> }>;
    };
    const message = messages.messages.find((item) =>
      item.To.some((address) => address.Address === recipient),
    );
    expect(message).toBeDefined();
    const detailResponse = await request.get(
      `http://127.0.0.1:8025/api/v1/message/${message!.ID}`,
    );
    const detail = (await detailResponse.json()) as { Text: string };
    expect(detail.Text).toContain(captureUrl);

    const capture = await page.request.get(captureUrl, { maxRedirects: 0 });
    expect(capture.status()).toBe(303);
    await page.goto("/auth/confirm");
    await expect(page.getByRole("button", { name: "Continuar a Umbral" })).toBeVisible();
  });
});
