import http from "node:http";

const port = Number(process.env.IDENTITY_MOCK_PORT || 4010);

const server = http.createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/healthz") {
    response.writeHead(200, { "Content-Type": "text/plain" });
    response.end("ok");
    return;
  }

  if (request.method === "POST" && request.url === "/api/v1/auth/magic-link-requests") {
    response.writeHead(202, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ status: 202, message: "Si la dirección está habilitada, recibirás un enlace para continuar." }));
    return;
  }

  if (request.method === "POST" && request.url === "/api/v1/auth/magic-link-confirmations") {
    response.writeHead(204, {
      "Cache-Control": "private, no-store",
      "Set-Cookie": "umbral_local_session=e2e-session; Path=/; HttpOnly; Secure; SameSite=Lax",
    });
    response.end();
    return;
  }

  if (request.method === "POST" && request.url === "/api/v1/auth/logout") {
    response.writeHead(204, {
      "Cache-Control": "private, no-store",
      "Set-Cookie": "umbral_local_session=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax",
    });
    response.end();
    return;
  }

  response.writeHead(404, { "Content-Type": "application/problem+json" });
  response.end(JSON.stringify({ detail: "not found" }));
});

server.listen(port, "127.0.0.1");
process.on("SIGTERM", () => server.close(() => process.exit(0)));
process.on("SIGINT", () => server.close(() => process.exit(0)));
