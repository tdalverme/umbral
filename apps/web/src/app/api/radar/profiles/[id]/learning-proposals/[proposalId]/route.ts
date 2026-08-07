import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function PUT(
  request: Request,
  { params }: { params: Promise<{ id: string; proposalId: string }> },
): Promise<NextResponse> {
  const { id, proposalId } = await params;
  const body = await request.json();
  const response = await forwardRadarRequest(
    `/api/v1/search-profiles/${id}/learning-proposals/${proposalId}`,
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    request,
  );
  return forwardJson(response) as Promise<NextResponse>;
}
