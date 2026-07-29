export function hasQueryParameters(request: Request): boolean {
  return new URL(request.url).searchParams.size > 0;
}

export function jsonResponse(body: unknown, status = 200, contentType = "application/json"): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": `${contentType}; charset=utf-8`,
    },
  });
}

export function invalidRequestResponse(): Response {
  return jsonResponse(
    {
      type: "about:blank",
      title: "Invalid request",
      status: 400,
    },
    400,
    "application/problem+json",
  );
}

export function unavailableResponse(): Response {
  return jsonResponse(
    {
      type: "about:blank",
      title: "Runtime unavailable",
      status: 503,
    },
    503,
    "application/problem+json",
  );
}
