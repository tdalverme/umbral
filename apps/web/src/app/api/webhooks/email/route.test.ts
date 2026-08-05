import { describe, expect, it, vi } from "vitest";

const { forwardIdentityRequest } = vi.hoisted(() => ({ forwardIdentityRequest: vi.fn() }));

vi.mock("@/lib/api/server", () => ({ forwardIdentityRequest }));

import { POST } from "./route";

describe("POST /api/webhooks/email", () => {
  it("forwards the raw Resend envelope with only the required Svix headers", async () => {
    const rawBody = '{\n  "id": "evt-1", "data": {"email_id": "email-1"}\n}';
    forwardIdentityRequest.mockResolvedValue(
      new Response(null, { status: 204, headers: { "content-type": "text/plain" } }),
    );

    await POST(
      new Request("https://preview.umbral.invalid/api/webhooks/email", {
        method: "POST",
        headers: {
          "content-type": "application/cloudevents+json",
          "svix-id": "msg_evt_1",
          "svix-timestamp": "1785600000",
          "svix-signature": "v1,signed",
          "x-untrusted": "must-not-forward",
        },
        body: rawBody,
      }),
    );

    const [, init] = forwardIdentityRequest.mock.calls[0] as [string, RequestInit];
    expect(forwardIdentityRequest).toHaveBeenCalledWith(
      "/api/v1/integrations/email/resend-events",
      expect.objectContaining({ method: "POST" }),
    );
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe(rawBody);
    expect(new Headers(init.headers)).toEqual(
      new Headers({
        "content-type": "application/cloudevents+json",
        "svix-id": "msg_evt_1",
        "svix-timestamp": "1785600000",
        "svix-signature": "v1,signed",
      }),
    );
  });
});
