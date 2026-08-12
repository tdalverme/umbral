import { apiBaseUrl } from "@/lib/api/server";

/** Forwards a product request to the API keeping the session cookie and BFF token. */
export async function forwardRadarRequest(
  path: string,
  init: RequestInit = {},
  incoming?: Request,
): Promise<Response> {
  const headers = new Headers(init.headers);
  const cookie = incoming?.headers.get("cookie");
  if (cookie) headers.set("Cookie", cookie);
  const contentType = incoming?.headers.get("content-type");
  if (contentType && !headers.has("Content-Type")) headers.set("Content-Type", contentType);
  headers.set("X-Umbral-BFF-Token", process.env.UMBRAL_BFF_TOKEN || "local-bff-token");
  if (!headers.has("X-Correlation-ID")) headers.set("X-Correlation-ID", crypto.randomUUID());
  return fetch(`${apiBaseUrl()}${path}`, { ...init, headers, cache: "no-store" });
}

/** Serializes a JSON body response keeping the API status code. */
export async function forwardJson(response: Response): Promise<Response> {
  const body = await response.text();
  return new Response(body, {
    status: response.status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

/** Forwards an SSE response without buffering (R-12). */
export async function forwardStream(response: Response): Promise<Response> {
  if (!response.ok || response.body === null) {
    return forwardJson(response);
  }
  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-store",
      "X-Accel-Buffering": "no",
    },
  });
}
