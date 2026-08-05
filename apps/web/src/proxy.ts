import { NextResponse, type NextRequest } from "next/server";

import { isPublicHealthPath, verifyAccessJwt } from "./lib/access/cloudflare";
import { resolveWebAccessMode } from "./lib/access/policy";

export async function proxy(request: NextRequest): Promise<NextResponse> {
  const accessMode = resolveWebAccessMode(process.env.UMBRAL_ACCESS_MODE);
  if (accessMode === null) {
    return new NextResponse("Access required", { status: 401 });
  }
  if (accessMode === "product_session") {
    return NextResponse.next();
  }
  if (isPublicHealthPath(request.nextUrl.pathname)) {
    return NextResponse.next();
  }
  if (
    process.env.NODE_ENV !== "production" &&
    process.env.UMBRAL_E2E_BYPASS_ACCESS === "1"
  ) {
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
