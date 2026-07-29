import { createClient, type Client } from "./generated/client";

function apiBaseUrl(): string {
  const baseUrl = process.env.UMBRAL_API_BASE_URL;
  if (!baseUrl) {
    throw new Error("UMBRAL_API_BASE_URL is required for server API requests");
  }
  return baseUrl;
}

export function createServerApiClient(options?: { correlationId?: string }): Client {
  const headers = options?.correlationId
    ? { "X-Correlation-Id": options.correlationId }
    : undefined;
  return createClient({ baseUrl: apiBaseUrl(), headers });
}

export async function forwardIdentityRequest(path: string, init: RequestInit = {}): Promise<globalThis.Response> {
  const baseUrl = apiBaseUrl();
  const headers = new Headers(init.headers);
  headers.set("X-Umbral-BFF-Token", process.env.UMBRAL_BFF_TOKEN || "local-bff-token");
  headers.set("X-Correlation-ID", crypto.randomUUID());
  return fetch(`${baseUrl}${path}`, { ...init, headers, cache: "no-store" });
}
