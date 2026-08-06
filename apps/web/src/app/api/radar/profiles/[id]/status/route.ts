import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }): Promise<NextResponse> {
  const { id } = await params;
  const url = new URL(request.url);
  const expectedVersion = url.searchParams.get("expected_version");
  const body = await request.text();
  const path = `/api/v1/search-profiles/${id}/status?expected_version=${encodeURIComponent(expectedVersion ?? "1")}`;
  const response = await forwardRadarRequest(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  }, request);
  return forwardJson(response) as Promise<NextResponse>;
}
