import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function GET(request: Request): Promise<NextResponse> {
  const url = new URL(request.url);
  const searchProfileId = url.searchParams.get("search_profile_id");
  const path = `/api/v1/chat/sessions${
    searchProfileId ? `?search_profile_id=${encodeURIComponent(searchProfileId)}` : ""
  }`;
  const response = await forwardRadarRequest(path, {}, request);
  return forwardJson(response) as Promise<NextResponse>;
}

export async function POST(request: Request): Promise<NextResponse> {
  const response = await forwardRadarRequest("/api/v1/chat/sessions", { method: "POST", body: await request.text() }, request);
  return forwardJson(response) as Promise<NextResponse>;
}
