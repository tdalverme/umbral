import { NextResponse } from "next/server";

import { forwardRadarRequest, forwardStream } from "@/lib/radar/server";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ sessionId: string; runId: string }> },
): Promise<NextResponse> {
  const { sessionId, runId } = await params;
  const response = await forwardRadarRequest(
    `/api/v1/chat/sessions/${sessionId}/runs/${runId}/decision`,
    { method: "POST", body: await request.text() },
    request,
  );
  return forwardStream(response) as Promise<NextResponse>;
}
