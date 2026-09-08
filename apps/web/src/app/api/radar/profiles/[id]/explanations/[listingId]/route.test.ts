import { beforeEach, describe, expect, it, vi } from "vitest";

const forwardRadarRequest = vi.fn();
const forwardJson = vi.fn((response) => response);

vi.mock("@/lib/radar/server", () => ({ forwardRadarRequest, forwardJson }));

describe("selected explanation BFF", () => {
  beforeEach(() => vi.clearAllMocks());

  it("forwards include_narrative with the run id", async () => {
    forwardRadarRequest.mockResolvedValue(new Response("{}"));
    const { GET } = await import("./route");
    await GET(
      new Request("https://umbral.test/api?run_id=run-1&include_narrative=true"),
      { params: Promise.resolve({ id: "profile-1", listingId: "listing-1" }) },
    );
    expect(forwardRadarRequest).toHaveBeenCalledWith(
      "/api/v1/search-profiles/profile-1/explanations/listing-1?run_id=run-1&include_narrative=true",
      {},
      expect.any(Request),
    );
  });
});
