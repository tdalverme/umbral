import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

async function postAction(action: string, request: Request, params: { id: string; proposalId: string }): Promise<NextResponse> {
  const { id, proposalId } = await Promise.resolve(params);
  const response = await forwardRadarRequest(
    `/api/v1/search-profiles/${id}/learning-proposals/${proposalId}/${action}`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
    request,
  );
  return forwardJson(response) as Promise<NextResponse>;
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string; proposalId: string }> },
): Promise<NextResponse> {
  const resolved = await params;
  return postAction("confirm", request, resolved);
}
