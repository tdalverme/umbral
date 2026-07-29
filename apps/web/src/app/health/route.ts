import {
  correlationIdFor,
  hasQueryParameters,
  invalidRequestResponse,
  jsonResponse,
} from "@/lib/runtime/http";

export function GET(request: Request): Response {
  if (hasQueryParameters(request)) return invalidRequestResponse();
  return jsonResponse({ status: "alive" }, 200, "application/json", correlationIdFor(request));
}
