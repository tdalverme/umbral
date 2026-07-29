import { NextResponse, type NextRequest } from "next/server";

import { isPublicHealthPath, verifyAccessJwt } from "./lib/access/cloudflare";

export async function proxy(request: NextRequest): Promise<NextResponse> {
  if (isPublicHealthPath(request.nextUrl.pathname)) {
    return NextResponse.next();
  }
  const token = request.headers.get("cf-access-jwt-assertion");
  const publicKey = process.env.CF_ACCESS_PUBLIC_KEY;
  const valid =
    token !== null &&
    publicKey !== undefined &&
    (await verifyAccessJwt(token, publicKey, Math.floor(Date.now() / 1000)));
  if (!valid) {
    return new NextResponse("Access required", { status: 401 });
  }
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
