import {
  correlationIdFor,
  hasQueryParameters,
  invalidRequestResponse,
  jsonResponse,
} from "@/lib/runtime/http";
import { loadRuntimeManifest, type RuntimeManifest } from "@/lib/runtime/manifest";

function readyPayload(manifest: RuntimeManifest) {
  return {
    surface: "web",
    state: "ready",
    observed_at: new Date().toISOString(),
    release_id: manifest.release_id,
    checks: [
      {
        name: "runtime_config",
        state: "ready",
        critical: true,
      },
    ],
  };
}

function unavailablePayload() {
  return {
    surface: "web",
    state: "not_ready",
    observed_at: new Date().toISOString(),
    release_id: process.env.UMBRAL_RELEASE_ID?.trim() || "unavailable",
    checks: [
      {
        name: "runtime_config",
        state: "unavailable",
        critical: true,
        code: "runtime_config.unavailable",
      },
    ],
  };
}

export async function GET(request: Request): Promise<Response> {
  if (hasQueryParameters(request)) return invalidRequestResponse();
  const correlationId = correlationIdFor(request);
  try {
    const payload = readyPayload(await loadRuntimeManifest());
    const apiBaseUrl = process.env.UMBRAL_API_BASE_URL;
    const bffToken = process.env.UMBRAL_BFF_TOKEN;
    if (!apiBaseUrl || !bffToken) throw new Error("runtime heartbeat unavailable");
    const heartbeat = await fetch(`${apiBaseUrl}/internal/runtime/web-heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Umbral-BFF-Token": bffToken },
      body: JSON.stringify({ state: payload.state, checks: Object.fromEntries(payload.checks.map((check) => [check.name, check.state])) }),
      cache: "no-store",
    });
    if (heartbeat.status !== 204) throw new Error("runtime heartbeat unavailable");
    return jsonResponse(payload, 200, "application/json", correlationId);
  } catch {
    return jsonResponse(unavailablePayload(), 503, "application/json", correlationId);
  }
}
