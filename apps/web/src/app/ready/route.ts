import { hasQueryParameters, invalidRequestResponse, jsonResponse } from "@/lib/runtime/http";
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
  try {
    return jsonResponse(readyPayload(await loadRuntimeManifest()));
  } catch {
    return jsonResponse(unavailablePayload(), 503);
  }
}
