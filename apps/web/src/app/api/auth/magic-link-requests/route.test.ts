import { beforeEach, describe, expect, it, vi } from "vitest";

const { forwardIdentityRequest } = vi.hoisted(() => ({ forwardIdentityRequest: vi.fn() }));
vi.mock("@/lib/api/server", () => ({ forwardIdentityRequest }));
vi.mock("@/lib/auth/origin", () => ({ originFingerprint: () => "origin" }));

import { POST } from "./route";

describe("POST /api/auth/magic-link-requests", () => {
  beforeEach(() => vi.resetAllMocks());

  it("preserves the smoke correlation through the BFF", async () => {
    forwardIdentityRequest.mockResolvedValue(new Response('{"message":"accepted"}', { status: 202 }));

    await POST(new Request("https://preview.example.test/api/auth/magic-link-requests", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Correlation-ID": "00000000-0000-0000-0000-000000000701" },
      body: '{"email":"invitee@example.test"}',
    }));

    expect(forwardIdentityRequest).toHaveBeenCalledWith("/api/v1/auth/magic-link-requests", expect.objectContaining({
      headers: expect.objectContaining({ "X-Correlation-ID": "00000000-0000-0000-0000-000000000701" }),
    }));
  });
});
