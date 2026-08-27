import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

const webRoot = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: webRoot,
  resolve: {
    alias: {
      "@": path.resolve(webRoot, "src"),
      "next/font/google": path.resolve(webRoot, "src/test/mocks/next-font-google.ts"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: [path.resolve(webRoot, "src/test/setup.ts")],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["node_modules", ".next", "playwright-report", "test-results"],
  },
});
