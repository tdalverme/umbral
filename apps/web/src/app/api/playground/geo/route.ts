import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function POST(request: Request): Promise<NextResponse> {
  const response = await forwardRadarRequest("/api/v1/playground/geo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  }, request);
  return forwardJson(response) as Promise<NextResponse>;
}

