import { NextResponse } from "next/server";

import { forwardRadarRequest, forwardJson } from "@/lib/radar/server";

export async function GET(request: Request): Promise<NextResponse> {
  const response = await forwardRadarRequest("/api/v1/agent/ops/overview", {}, request);
  return new NextResponse(await (await forwardJson(response)).text(), {
    status: response.status,
    headers: {
      "Cache-Control": "private, no-store",
      "Content-Type": "application/json",
    },
  });
}
