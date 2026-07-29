import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../../contracts/openapi/v1/openapi.json",
  output: "src/lib/api/generated",
  plugins: [
    "@hey-api/typescript",
    "@hey-api/client-fetch",
    "@hey-api/sdk",
    "@tanstack/react-query",
  ],
});
