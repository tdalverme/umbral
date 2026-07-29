export function hasQueryParameters(request: Request): boolean {
  return new URL(request.url).searchParams.size > 0;
}

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function correlationIdFor(request: Request): string {
  const candidate = request.headers.get("x-correlation-id");
  return candidate && UUID_PATTERN.test(candidate) ? candidate : crypto.randomUUID();
}

export function jsonResponse(
  body: unknown,
  status = 200,
  contentType = "application/json",
  correlationId?: string,
): Response {
  const headers = new Headers({
    "Cache-Control": "no-store",
    "Content-Type": `${contentType}; charset=utf-8`,
  });
  if (correlationId) headers.set("X-Correlation-Id", correlationId);
  return new Response(JSON.stringify(body), {
    status,
    headers,
  });
}

export function invalidRequestResponse(correlationId?: string): Response {
  return jsonResponse(
    {
      type: "about:blank",
      title: "Invalid request",
      status: 400,
    },
    400,
    "application/problem+json",
    correlationId,
  );
}

export function unavailableResponse(correlationId?: string): Response {
  return jsonResponse(
    {
      type: "about:blank",
      title: "Runtime unavailable",
      status: 503,
    },
    503,
    "application/problem+json",
    correlationId,
  );
}
