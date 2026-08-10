import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest, forwardStream } from "@/lib/radar/server";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> },
): Promise<NextResponse> {
  const { sessionId } = await params;
  const response = await forwardRadarRequest(
    `/api/v1/chat/sessions/${sessionId}/messages`,
    {},
    request,
  );
  return forwardJson(response) as Promise<NextResponse>;
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ sessionId: string }> },
): Promise<NextResponse> {
  const { sessionId } = await params;
  const response = await forwardRadarRequest(
    `/api/v1/chat/sessions/${sessionId}/messages`,
    { method: "POST", body: await request.text() },
    request,
  );
  return forwardStream(response) as Promise<NextResponse>;
}
