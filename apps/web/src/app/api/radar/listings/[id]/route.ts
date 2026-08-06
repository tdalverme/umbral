import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }): Promise<NextResponse> {
  const { id } = await params;
  const response = await forwardRadarRequest(`/api/v1/listings/${id}`, {}, request);
  return forwardJson(response) as Promise<NextResponse>;
}
