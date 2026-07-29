import { createClient, type Client } from "./generated/client";

export function createBrowserApiClient(correlationId?: string): Client {
  return createClient({
    baseUrl: window.location.origin,
    headers: correlationId ? { "X-Correlation-Id": correlationId } : undefined,
  });
}
