import { CAPTURE_COOKIE, sealCapture, unsealCapture } from "./cookies";

describe("capture cookie", () => {
  it("round-trips encrypted transient values and rejects tampering", () => {
    const sealed = sealCapture("00000000-0000-0000-0000-000000000000", "a".repeat(64));
    expect(CAPTURE_COOKIE).toBe("umbral_capture");
    expect(unsealCapture(sealed)).toEqual({
      attemptId: "00000000-0000-0000-0000-000000000000",
      tokenHash: "a".repeat(64),
    });
    expect(unsealCapture(`${sealed}x`)).toBeNull();
  });
});
