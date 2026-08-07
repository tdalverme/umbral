import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; proposalId: string }> },
): Promise<NextResponse> {
  const { id, proposalId } = await params;
  const response = await forwardRadarRequest(
    `/api/v1/search-profiles/${id}/learning-proposals/${proposalId}/undo`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
    request,
  );
  return forwardJson(response) as Promise<NextResponse>;
}
