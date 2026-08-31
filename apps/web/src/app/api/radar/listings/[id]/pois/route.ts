import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }): Promise<NextResponse> {
  const { id } = await params;
  const url = new URL(request.url);
  const qs = url.searchParams.toString();
  const path = `/api/v1/listings/${id}/pois${qs ? `?${qs}` : ""}`;
  const response = await forwardRadarRequest(path, {}, request);
  return forwardJson(response) as Promise<NextResponse>;
}
