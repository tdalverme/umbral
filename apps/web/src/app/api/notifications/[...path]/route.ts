import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

type RouteContext = { params: Promise<{ path: string[] }> };

/** BFF for the notifications surface: forwards to the product API keeping the
 * session cookie and BFF token (same pattern as the radar routes). */
async function forward(request: Request, path: string[], init: RequestInit): Promise<NextResponse> {
  const suffix = path.map(encodeURIComponent).join("/");
  const url = new URL(request.url);
  const query = url.search;
  const target = `/api/v1/notifications/${suffix}${query}`;
  const response = await forwardRadarRequest(target, init, request);
  return forwardJson(response) as Promise<NextResponse>;
}

export async function GET(request: Request, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  return forward(request, path, {});
}

export async function PUT(request: Request, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  const body = await request.text();
  return forward(request, path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

export async function PATCH(request: Request, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  const body = await request.text();
  return forward(request, path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body,
  });
}

export async function POST(request: Request, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  const body = await request.text();
  return forward(request, path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
}
