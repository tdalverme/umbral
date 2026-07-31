import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const repositoryRoot = path.resolve(__dirname, "../../");
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3000";

export default defineConfig({
  testDir: path.resolve(repositoryRoot, "tests/e2e"),
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL,
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: "node tests/e2e/mock-identity-api.mjs",
      cwd: repositoryRoot,
      url: "http://127.0.0.1:4010/healthz",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command:
        "npm run dev --workspace @umbral/web -- --hostname 127.0.0.1 --port 3000",
      cwd: repositoryRoot,
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        UMBRAL_API_BASE_URL: "http://127.0.0.1:4010",
        UMBRAL_BFF_TOKEN: "e2e-bff-token",
        UMBRAL_E2E_BYPASS_ACCESS: "1",
      },
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
