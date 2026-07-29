import { hasQueryParameters, invalidRequestResponse, jsonResponse, unavailableResponse } from "@/lib/runtime/http";
import { loadRuntimeManifest, versionFromManifest } from "@/lib/runtime/manifest";

export async function GET(request: Request): Promise<Response> {
  if (hasQueryParameters(request)) return invalidRequestResponse();
  try {
    return jsonResponse(versionFromManifest(await loadRuntimeManifest()));
  } catch {
    return unavailableResponse();
  }
}
