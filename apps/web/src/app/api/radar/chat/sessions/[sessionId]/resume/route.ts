import { NextResponse } from "next/server";

import { forwardRadarRequest, forwardStream } from "@/lib/radar/server";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> },
): Promise<NextResponse> {
  const { sessionId } = await params;
  const response = await forwardRadarRequest(
    `/api/v1/chat/sessions/${sessionId}/resume`,
    { method: "POST", body: "{}" },
    request,
  );
  return forwardStream(response) as Promise<NextResponse>;
}
