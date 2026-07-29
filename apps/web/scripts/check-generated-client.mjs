import { execFileSync } from "node:child_process";

const generatedClientPath = "src/lib/api/generated";
const changes = execFileSync(
  "git",
  ["status", "--short", "--", generatedClientPath],
  { encoding: "utf8" },
).trim();

if (changes) {
  process.stderr.write(
    "Generated OpenAPI client drift detected. Regenerate and commit the output:\n" +
      `${changes}\n`,
  );
  process.exitCode = 1;
}
