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
  webServer: {
    command:
      "npm run dev --workspace @umbral/web -- --hostname 127.0.0.1 --port 3000",
    cwd: repositoryRoot,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
