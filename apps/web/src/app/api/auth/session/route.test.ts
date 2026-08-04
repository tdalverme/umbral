import { beforeEach, describe, expect, it, vi } from "vitest";

const { forwardIdentityRequest } = vi.hoisted(() => ({ forwardIdentityRequest: vi.fn() }));
vi.mock("@/lib/api/server", () => ({ forwardIdentityRequest }));

import { GET } from "./route";

describe("GET /api/auth/session", () => {
  beforeEach(() => vi.resetAllMocks());

  it("forwards only the session cookie to the private identity API", async () => {
    forwardIdentityRequest.mockResolvedValue(
      new Response(JSON.stringify({ roles: ["user"] }), { status: 200 }),
    );

    const response = await GET(new Request("https://preview.example.test/api/auth/session", {
      headers: { Cookie: "umbral_local_session=private-session; other=ignored" },
    }));

    expect(forwardIdentityRequest).toHaveBeenCalledWith("/api/v1/auth/session", {
      headers: { Cookie: "umbral_local_session=private-session" },
    });
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ roles: ["user"] });
  });
});
