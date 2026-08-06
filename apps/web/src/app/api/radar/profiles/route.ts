import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function GET(request: Request): Promise<NextResponse> {
  const url = new URL(request.url);
  const status = url.searchParams.get("status");
  const path = status ? `/api/v1/search-profiles?status=${encodeURIComponent(status)}` : "/api/v1/search-profiles";
  const response = await forwardRadarRequest(path, {}, request);
  return forwardJson(response) as Promise<NextResponse>;
}

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();
  const response = await forwardRadarRequest("/api/v1/search-profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  }, request);
  return forwardJson(response) as Promise<NextResponse>;
}
