import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; listingId: string }> },
): Promise<NextResponse> {
  const { id, listingId } = await params;
  const url = new URL(request.url);
  const search = new URLSearchParams();
  const runId = url.searchParams.get("run_id");
  if (runId) search.set("run_id", runId);
  const query = search.toString();
  const path = `/api/v1/search-profiles/${id}/explanations/${listingId}${query ? `?${query}` : ""}`;
  const response = await forwardRadarRequest(path, {}, request);
  return forwardJson(response) as Promise<NextResponse>;
}
