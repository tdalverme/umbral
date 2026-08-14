import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET as health } from "./health/route";
import { GET as ready } from "./ready/route";
import { GET as version } from "./version/route";

const previousManifest = process.env.UMBRAL_RELEASE_MANIFEST;

function manifestPath(): string {
  return `${process.cwd()}/../../tests/fixtures/release-manifests/valid.json`;
}

describe("web runtime routes", () => {
  beforeEach(() => {
    process.env.UMBRAL_RELEASE_MANIFEST = manifestPath();
    process.env.UMBRAL_API_BASE_URL = "http://api.test.internal";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(null, { status: 204 })),
    );
  });

  afterEach(() => {
    if (previousManifest === undefined) {
      delete process.env.UMBRAL_RELEASE_MANIFEST;
    } else {
      process.env.UMBRAL_RELEASE_MANIFEST = previousManifest;
    }
    delete process.env.UMBRAL_API_BASE_URL;
    vi.unstubAllGlobals();
  });

  it("returns a cache-free liveness response without querying dependencies", async () => {
    const response = await health(new Request("http://localhost/health"));

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({ status: "alive" });
  });

  it("reports web readiness from local release configuration only", async () => {
    const response = await ready(new Request("http://localhost/ready"));

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const payload = await response.json();
    expect(payload).toMatchObject({
      surface: "web",
      state: "ready",
      release_id: "foundation-20260101",
      checks: [
        {
          name: "runtime_config",
          state: "ready",
          critical: true,
        },
      ],
    });
  });

  it("derives immutable version fields and web digest from the manifest", async () => {
    const response = await version(new Request("http://localhost/version"));

    expect(response.status).toBe(200);
    expect(response.headers.get("cache-control")).toBe("no-store");
    const payload = await response.json();
    expect(payload).toMatchObject({
      surface: "web",
      release_id: "foundation-20260101",
      git_sha: "0123456789abcdef0123456789abcdef01234567",
      artifact_digest: "sha256:1111111111111111111111111111111111111111111111111111111111111111",
      contract_major: 1,
      database_revision: "foundation_0001",
      built_at: "2026-01-01T00:00:00Z",
    });
    const secondResponse = await version(new Request("http://localhost/version"));
    expect(await secondResponse.json()).toEqual(payload);
  });
});
