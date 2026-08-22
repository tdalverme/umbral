import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function GET(request: Request): Promise<NextResponse> {
  const response = await forwardRadarRequest("/api/v1/playground/fixtures", {}, request);
  return forwardJson(response) as Promise<NextResponse>;
}

