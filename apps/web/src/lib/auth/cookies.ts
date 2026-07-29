import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";

export const CAPTURE_COOKIE = "umbral_capture";

function secret(): string {
  return process.env.UMBRAL_BFF_TOKEN || "local-bff-token";
}

function key(): Buffer {
  return createHash("sha256").update(secret()).digest();
}

export function sealCapture(attemptId: string, tokenHash: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key(), iv);
  const payload = Buffer.from(JSON.stringify({ attemptId, tokenHash }));
  const encrypted = Buffer.concat([cipher.update(payload), cipher.final()]);
  return [iv, cipher.getAuthTag(), encrypted].map((part) => part.toString("base64url")).join(".");
}

export function unsealCapture(value: string | undefined): { attemptId: string; tokenHash: string } | null {
  if (!value) return null;
  const [ivEncoded, tagEncoded, payloadEncoded] = value.split(".");
  if (!ivEncoded || !tagEncoded || !payloadEncoded) return null;
  try {
    const decipher = createDecipheriv("aes-256-gcm", key(), Buffer.from(ivEncoded, "base64url"));
    decipher.setAuthTag(Buffer.from(tagEncoded, "base64url"));
    const payload = Buffer.concat([
      decipher.update(Buffer.from(payloadEncoded, "base64url")),
      decipher.final(),
    ]);
    const parsed = JSON.parse(payload.toString("utf8")) as { attemptId?: string; tokenHash?: string };
    if (!parsed.attemptId || !parsed.tokenHash || parsed.tokenHash.length < 32) return null;
    return { attemptId: parsed.attemptId, tokenHash: parsed.tokenHash };
  } catch {
    return null;
  }
}
