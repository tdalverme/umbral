import { describe, expect, it } from "vitest";

import { metadataSignal } from "./telemetry";

describe("metadataSignal", () => {
  it("keeps route templates and rejects raw transport content", () => {
    const signal = metadataSignal({
      correlationId: "1d0e27a2-4bc9-48b0-bc5f-c33df906a990",
      operation: "request.completed",
      routeTemplate: "/listings/{listing_id}",
      method: "GET",
      statusCode: 200,
    });

    expect(signal).toEqual({
      correlation_id: "1d0e27a2-4bc9-48b0-bc5f-c33df906a990",
      operation: "request.completed",
      route_template: "/listings/{listing_id}",
      http_method: "GET",
      status_code: 200,
    });
    expect(() => metadataSignal({ operation: "request.completed", url: "https://private.invalid/?secret=canary" })).toThrow();
  });
});
