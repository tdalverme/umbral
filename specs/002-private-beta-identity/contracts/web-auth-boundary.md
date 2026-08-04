# Contract: Web BFF, Capture, Confirmation, and Cookies

## Trust Topology

```text
browser
  -> Cloudflare public Umbral web origin
    -> Next.js route/server action (BFF)
      -> private FastAPI
        -> PostgreSQL / worker / provider Adapters
```

FastAPI and provider secrets are never browser-addressable. Next.js may proxy
only the closed identity operations declared here and uses a distinct
environment BFF credential.

## Anonymous Routes

- `GET /health`
- `GET /login`
- `POST /api/auth/magic-link-requests`
- `GET /auth/capture`
- `GET /auth/confirm`
- the explicit confirmation server action / BFF `POST`
- required static assets
- `POST /api/webhooks/email` for provider delivery, signature required

Every other product route uses the protected layout/server guard. The Render
origin remains disabled; only the Cloudflare web origin is public.

## Request Route

`POST /api/auth/magic-link-requests`:

1. applies same-origin/CSRF protection and a bounded body limit;
2. ignores any browser-supplied forwarding or internal headers;
3. derives client address only from the trusted platform header;
4. creates environment HMAC origin fingerprint;
5. forwards email, fingerprint, correlation, and BFF credential to FastAPI;
6. returns the canonical neutral response and no provider/rate metadata;
7. sets `Cache-Control: no-store`.

The BFF must not normalize eligibility, call providers, or branch the visible
response.

## Email URL

Approved form:

```text
https://<environment-web-origin>/auth/capture
  ?attempt_id=<uuid>
  &token_hash=<bounded-provider-token-hash>
```

No arbitrary `next` or redirect parameter is accepted. The destination after
success is configured server-side. Each environment allowlists only its own
canonical/preview origin plus loopback in local mode.

## Capture Route

`GET /auth/capture`:

- validates `attempt_id` UUID and bounded token-hash shape only;
- does not call FastAPI or Supabase verification;
- stores both values in an authenticated-encrypted, short-lived
  `HttpOnly; Secure; SameSite=Strict; Path=/auth` transient cookie;
- cookie lifetime is at most five minutes and never exceeds the underlying link;
- returns `303 See Other` to `/auth/confirm` without query parameters;
- responds `Cache-Control: no-store`, `Referrer-Policy: no-referrer`;
- token query/header/cookie values are redacted from access logs and Sentry;
- Cloudflare/web platform logging for `/auth/capture` omits query strings, and
  the release canary verifies the token hash is absent from edge logs.

A scanner GET therefore cannot consume a proof.

## Confirmation Page and POST

`GET /auth/confirm` renders an accessible page with:

- explicit “Continuar a Umbral” submit button;
- generic expired/invalid recovery without membership disclosure;
- no token, email, provider name, or internal failure detail in HTML/client JS;
- keyboard/focus/axe coverage.

The server action or BFF `POST`:

1. reads the transient cookie and clears it after success or terminal denial;
2. applies same-origin/CSRF checks;
3. forwards attempt/token server-to-server;
4. copies only the allowlisted product `Set-Cookie` header from FastAPI;
5. redirects to the configured protected landing route on success;
6. maps `410` to “solicitar un enlace nuevo”, `403` to controlled support, and
   `503` to retry-later without provider details while retaining the transient
   cookie until its short expiry;
7. never returns the token in JSON, HTML, URL, or client state.

Duplicate POST cannot create a second session. If the first response was lost,
the consumed link may require a new request; the opaque session token is not
persisted for cookie replay.

## Product Session Cookie

Remote:

```text
Name: __Host-umbral_session
Secure: true
HttpOnly: true
SameSite: Lax
Path: /
Domain: absent
```

Local HTTP uses `umbral_local_session` with `HttpOnly`, `SameSite=Lax`,
`Path=/`, no Domain, and `Secure=false`. Production configuration rejects the
local name or insecure form.

Cookie value has at least 256 random bits and is opaque. Only FastAPI generates
it. Next forwards it as a cookie to private FastAPI and does not decode it.
Logout expires the browser cookie even if API revocation is already complete.

## Origin Fingerprint

- Next trusts only the platform-provided address header on requests received
  through the configured Cloudflare/Render path.
- Any client `X-Forwarded-*`, `CF-Connecting-IP`,
  `X-Umbral-Origin-Fingerprint`, BFF credential, or correlation override is
  stripped/overwritten.
- Fingerprint is HMAC-SHA-256 using an environment secret and canonical address
  bytes; base64url without padding is sent to FastAPI.
- Raw address is not logged, traced, placed in audit, or sent to providers.
- Current/previous fingerprint key overlap is supported for one rolling window
  during planned rotation.

## CSRF and Cache Rules

- Mutating browser routes require same-origin `Origin`/`Host` validation and
  framework CSRF-safe server-action behavior.
- `SameSite` is defense in depth, not the only CSRF check.
- Auth/session responses are `private, no-store` and excluded from CDN/ISR.
- Responses carrying `Set-Cookie` are never cached.
- Login/confirm pages do not use background session polling that could extend
  inactivity.

## Environment Transition

Preview may keep Cloudflare Access before these routes. Production exposes the
anonymous route allowlist only after:

1. private API/BFF credential smoke;
2. redirect and issuer isolation;
3. invited success/non-invited neutral denial;
4. scanner GET non-consumption;
5. cookie attribute and logout checks;
6. role/ownership matrix;
7. rollback rehearsal.

Cloudflare remains the proxy/WAF; only its temporary email identity gate is
removed from production product access.
