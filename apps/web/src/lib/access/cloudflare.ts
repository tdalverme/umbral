import { PUBLIC_HEALTH_PATH } from "./policy";

export type AccessClaims = { aud: string | string[]; exp: number };

export const ACCESS_AUDIENCE = "umbral-runtime";

export function isPublicHealthPath(pathname: string): boolean {
  return pathname === PUBLIC_HEALTH_PATH;
}

export function validateAccessClaims(claims: AccessClaims, nowSeconds: number): boolean {
  const audience = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  return audience.includes(ACCESS_AUDIENCE) && claims.exp > nowSeconds;
}

function decodeBase64Url(value: string): Uint8Array<ArrayBuffer> {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const bytes = atob(padded);
  const output = new Uint8Array(bytes.length);
  for (let index = 0; index < bytes.length; index += 1) {
    output[index] = bytes.charCodeAt(index);
  }
  return output;
}

function decodeJson(value: string): Record<string, unknown> | null {
  try {
    const decoded = new TextDecoder().decode(decodeBase64Url(value));
    const parsed: unknown = JSON.parse(decoded);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function pemToDer(pem: string): ArrayBuffer {
  const body = pem.replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s/g, "");
  return decodeBase64Url(body).buffer;
}

export async function verifyAccessJwt(
  token: string,
  publicKeyPem: string,
  nowSeconds: number,
): Promise<boolean> {
  const parts = token.split(".");
  if (parts.length !== 3) return false;
  const header = decodeJson(parts[0]);
  const claims = decodeJson(parts[1]);
  if (header?.alg !== "RS256" || !claims) return false;
  const audience = claims.aud;
  const expiry = claims.exp;
  if (
    (typeof audience !== "string" && !Array.isArray(audience)) ||
    typeof expiry !== "number" ||
    !validateAccessClaims({ aud: audience as string | string[], exp: expiry }, nowSeconds)
  ) {
    return false;
  }
  try {
    const key = await crypto.subtle.importKey(
      "spki",
      pemToDer(publicKeyPem),
      { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
      false,
      ["verify"],
    );
    return crypto.subtle.verify(
      { name: "RSASSA-PKCS1-v1_5" },
      key,
      decodeBase64Url(parts[2]),
      new TextEncoder().encode(`${parts[0]}.${parts[1]}`),
    );
  } catch {
    return false;
  }
}
