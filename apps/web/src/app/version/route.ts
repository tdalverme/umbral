import {
  correlationIdFor,
  hasQueryParameters,
  invalidRequestResponse,
  jsonResponse,
  unavailableResponse,
} from "@/lib/runtime/http";
import { loadRuntimeManifest, versionFromManifest } from "@/lib/runtime/manifest";

export async function GET(request: Request): Promise<Response> {
  if (hasQueryParameters(request)) return invalidRequestResponse();
  const correlationId = correlationIdFor(request);
  try {
    return jsonResponse(
      versionFromManifest(await loadRuntimeManifest()),
      200,
      "application/json",
      correlationId,
    );
  } catch {
    return unavailableResponse(correlationId);
  }
}
