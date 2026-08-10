import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const url = new URL(request.url);
  const state = url.searchParams.get("state") ?? "pending";
  const response = await forwardRadarRequest(
    `/api/v1/search-profiles/${id}/update-proposals?state=${encodeURIComponent(state)}`,
    {},
    request,
  );
  return forwardJson(response) as Promise<NextResponse>;
}
