import { NextResponse } from "next/server";

import { forwardJson, forwardRadarRequest } from "@/lib/radar/server";

export async function POST(request: Request): Promise<NextResponse> {
  const body = await request.text();
  const response = await forwardRadarRequest("/api/v1/product-events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  }, request);
  return forwardJson(response) as Promise<NextResponse>;
}
