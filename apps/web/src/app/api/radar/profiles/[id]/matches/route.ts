import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }): Promise<NextResponse> {
  const { id } = await params;
  const url = new URL(request.url);
  const search = new URLSearchParams();
  for (const key of ["run_id", "page_size", "after_position"]) {
    const value = url.searchParams.get(key);
    if (value) search.set(key, value);
  }
  const query = search.toString();
  const path = `/api/v1/search-profiles/${id}/matches${query ? `?${query}` : ""}`;
  const response = await forwardRadarRequest(path, {}, request);
  return forwardJson(response) as Promise<NextResponse>;
}
