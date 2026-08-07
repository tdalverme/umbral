import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<NextResponse> {
  const { id } = await params;
  const body = await request.json();
  const response = await forwardRadarRequest(
    `/api/v1/search-profiles/${id}/feedback`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    request,
  );
  return forwardJson(response) as Promise<NextResponse>;
}
