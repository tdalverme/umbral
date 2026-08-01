import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { NextRequest } from "next/server";

import { proxy } from "../../proxy";

const originalAccessMode = process.env.UMBRAL_ACCESS_MODE;
const originalE2eBypass = process.env.UMBRAL_E2E_BYPASS_ACCESS;

function request(pathname: string): NextRequest {
  return new NextRequest(`https://preview.umbral.invalid${pathname}`);
}

describe("web access policy", () => {
  beforeEach(() => {
    delete process.env.UMBRAL_E2E_BYPASS_ACCESS;
  });

  afterEach(() => {
    if (originalAccessMode === undefined) {
      delete process.env.UMBRAL_ACCESS_MODE;
    } else {
      process.env.UMBRAL_ACCESS_MODE = originalAccessMode;
    }
    if (originalE2eBypass === undefined) {
      delete process.env.UMBRAL_E2E_BYPASS_ACCESS;
    } else {
      process.env.UMBRAL_E2E_BYPASS_ACCESS = originalE2eBypass;
    }
  });

  it("bypasses Cloudflare in product-session mode without creating a product session", async () => {
    process.env.UMBRAL_ACCESS_MODE = "product_session";

    const response = await proxy(request("/searches"));

    expect(response.status).toBe(200);
    expect(response.headers.get("set-cookie")).toBeNull();
  });

  it("keeps Cloudflare JWT verification in cloudflare mode", async () => {
    process.env.UMBRAL_ACCESS_MODE = "cloudflare";

    const response = await proxy(request("/login"));

    expect(response.status).toBe(401);
  });

  it("uses the exact anonymous environment-path allowlist", async () => {
    const { PUBLIC_ANONYMOUS_PATHS, isPublicAnonymousPath } = await import("./policy");

    expect(PUBLIC_ANONYMOUS_PATHS).toEqual([
      "/health",
      "/login",
      "/auth/capture",
      "/auth/confirm",
      "/api/auth/magic-link-requests",
      "/api/webhooks/email",
    ]);
    expect(isPublicAnonymousPath("/ready")).toBe(false);
  });

  it("fails closed for an unknown access mode", async () => {
    process.env.UMBRAL_ACCESS_MODE = "unsupported";

    const response = await proxy(request("/login"));

    expect(response.status).toBe(401);
  });
});
