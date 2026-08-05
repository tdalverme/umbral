import { createHmac } from "node:crypto";

/** Return a stable, minimized request-origin signal for abuse limits. */
export function originFingerprint(request: Request): string {
  const forwarded = request.headers.get("x-forwarded-for")?.split(",", 1)[0]?.trim();
  const source = forwarded || request.headers.get("x-real-ip") || "unknown";
  const key = process.env.IDENTITY_FINGERPRINT_KEY || process.env.UMBRAL_BFF_TOKEN || "local-identity-fingerprint-key";
  return createHmac("sha256", key).update(source).digest("hex");
}
