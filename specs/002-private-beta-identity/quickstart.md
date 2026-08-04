# Quickstart: Private Beta Identity

This is the target developer and acceptance flow after
`foundation-runtime` and this increment are implemented. Commands that do not
yet exist are implementation outputs, not current repository guarantees.

## 1. Prerequisites

- foundation runtime checks pass;
- Python/Node versions and lockfiles match the foundation plan;
- Docker is available for PostgreSQL, Redis, and Mailpit;
- no real Supabase/Resend secret is needed for the default local path.

From the repository root:

```powershell
uv sync --frozen --all-groups
npm ci
docker compose up -d postgres redis mailpit
uv run alembic upgrade head
```

Mailpit is local-only and should expose its UI on `http://127.0.0.1:8025`.

## 2. Local Configuration

Copy the project environment example using the repository's documented secret
workflow. Set non-secret local values equivalent to:

```text
UMBRAL_ENVIRONMENT=local
IDENTITY_PROVIDER=fake
EMAIL_PROVIDER=mailpit
IDENTITY_MAGIC_LINK_LIFETIME_SECONDS=900
IDENTITY_SESSION_IDLE_SECONDS=604800
IDENTITY_WEB_ORIGIN=http://127.0.0.1:3000
IDENTITY_CAPTURE_PATH=/auth/capture
IDENTITY_COOKIE_NAME=umbral_local_session
IDENTITY_COOKIE_SECURE=false
IDENTITY_REQUEST_EMAIL_LIMIT=3
IDENTITY_REQUEST_ORIGIN_LIMIT=20
IDENTITY_REQUEST_WINDOW_SECONDS=900
```

Fingerprint, BFF, and transient-cookie keys are generated through the
foundation secret mechanism. They are never committed, printed, or named
`NEXT_PUBLIC_*`. Production rejects fake providers, local cookie settings,
loopback redirects, shared keys, or a session/link duration different from the
specification.

## 3. Preload One Invitation

The controlled operation takes a stable actor/source, normalizes the email, and
records audit:

```powershell
$env:PYTHONPATH = "src"
uv run python -m umbral.ops.identity preload-invitation `
  --email invited@example.test `
  --actor-kind deployment `
  --actor-id local-developer `
  --source local_quickstart
```

Observed local status (2026-07-31): `umbral.ops.identity` currently exposes
report/export functions but no argparse entry point, so this command exits
without creating an invitation. The preload operation is exercised through
`AccessAdministration` in the identity integration fixtures until the
operator CLI composition is wired.

Running the same command again is idempotent only when normalized email,
state, and controlled source agree. It does not send email or grant a privileged
role.

## 4. Run the Three Surfaces

Use separate terminals:

```powershell
$env:PYTHONPATH = "src"
uv run uvicorn umbral.api.main:app --reload
```

```powershell
$env:PYTHONPATH = "src"
uv run python -m umbral.workers worker
```

```powershell
npm run dev
```

FastAPI remains private in remote environments. Local direct API access is for
development only; browser identity flows use `http://127.0.0.1:3000`.

## 5. Complete First Access

1. Open `http://127.0.0.1:3000/login`.
2. Request access for `invited@example.test`.
3. Observe the same neutral acknowledgement that an uninvited email receives.
4. Open Mailpit and follow the newest Umbral link.
5. Verify the first `GET /auth/capture` redirects to the clean confirmation
   page without consuming the link.
6. Press the explicit confirmation button.
7. Verify the browser reaches a protected page and receives only the local
   opaque session cookie.

Expected durable results:

- invitation is `accepted`;
- one active product user exists;
- one external fake-provider link exists;
- exactly one current `user` assignment exists;
- attempt is `consumed`;
- one active product session exists;
- correlated audit contains request, issue, consume, activation, link, role,
  session, and authorization events;
- no row/log/trace contains the token hash, full URL, raw origin, or cookie.

## 6. Repeat Access

Log out, request a new link for the same address, and confirm it.

Expected:

- same product-user ID and external-link ID;
- no new invitation or `user` role assignment;
- one new consumed attempt and one new session;
- the logged-out session remains revoked.

## 7. Exercise Safe Failure Paths

### Non-invited email

Request `not-in-cohort@example.test`.

- response/status/body match the invited request;
- no issue job or provider email exists;
- minimized request/audit evidence exists.

### Latest link wins

Request two allowed links, wait for both issue jobs, then submit the older one.

- older attempt is `superseded`;
- older link returns generic recoverable `410`;
- newest link can be consumed once.

### Scanner prefetch

Use an HTTP client to `GET` the capture URL twice without submitting the form.

- no provider verification;
- no consumed attempt or session;
- explicit POST still works before expiry.

### Exact limits

In integration tests, submit concurrent requests for one email/origin.

- first three email-dimension reservations may create eligible attempts;
- fourth creates no attempt/job/provider call and does not change the current
  issued link;
- first twenty origin-dimension reservations are admitted subject to email
  limits; 21st is origin-limited;
- after the rolling window ages out with no new request, another reservation is
  admitted.

Do not test this manually against production email.

### Seven-day idle boundary

Use the database-time integration fixture to set `last_activity_at` just before
and exactly at the boundary.

- allowed protected operation before seven full days updates activity;
- exactly seven full days expires rather than revives;
- denied/public/background operations do not update activity.

### Role and ownership

Run the finite matrix fixture. Administrator and operator may perform only
their explicit operational actions; neither can read another user's
representative private resource.

## 8. Optional Provider Conformance

For preview/provider validation, use isolated non-production projects and test
domains:

```text
IDENTITY_PROVIDER=supabase
EMAIL_PROVIDER=resend
SUPABASE_URL=<preview project>
SUPABASE_SECRET_KEY=<server only>
SUPABASE_EXPECTED_ISSUER=<preview issuer>
RESEND_API_KEY=<preview only>
RESEND_WEBHOOK_SECRET=<preview only>
IDENTITY_WEB_ORIGIN=<preview Umbral origin>
```

Before use, confirm against current provider docs/changelog:

- Supabase email OTP/magic-link expiry is 900 seconds;
- only preview redirect is allowlisted;
- open signup/browser provider keys are not exposed;
- Resend domain/test mode cannot send as production;
- click/open tracking is off;
- webhook signature and duplicate tests pass.

Preview and production use different projects, keys, webhook endpoints, BFF
credentials, fingerprint keys, and redirect origins.

## 9. Verification

Focused:

```powershell
uv run pytest tests/unit/identity
uv run pytest tests/contract/test_identity_provider.py tests/contract/test_email_provider.py
uv run pytest tests/integration/identity tests/migrations/test_identity_migration_harness.py
npm run test
npm run test:e2e:identity --workspace @umbral/web
```

Full:

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
npm run lint
npm run typecheck
npm run api:check
npm run build
npm run test:e2e
.\scripts\check.ps1
```

The release evidence additionally includes provider conformance, 20 timed beta
journeys, rejection corpus, redaction canaries, environment crossover
rejection, delivery/bounce event, production access-gate transition, and
rollback of the exact release manifest.

## 10. Local validation evidence (2026-07-31)

The documented dependency sync, `npm ci`, Docker services, Alembic upgrade,
API `/health` smoke, worker parser smoke, focused identity suite, and Mailpit
browser flow were executed successfully. The focused Python suite reported
46 passing tests; the identity Playwright suite reported 7 passing tests; the
full harness reported 199 passing Python tests and no blocking failures.

The harness requires npm 12 (`npm --version` reported `12.0.2`) and a writable
temporary directory on Windows. For this environment it was run with
`TEMP`/`TMP` pointed at a workspace-local temporary directory. Provider
conformance and release-preview steps remain intentionally outside this local
quickstart.

Acceptance evidence recorded in the same run:

- **SC-001**: 20 repetitions of the identity E2E file (140 scenario executions)
  passed with one worker.
- **SC-002**: unknown-address login remains neutral and provider failures create
  no user, link, or session.
- **SC-004**: ten duplicate confirmations leave exactly one session.
- **SC-008**: repeat login reuses the product user, external link, and role.
- **SC-009**: the seven-day idle boundary is covered by the access-flow and
  authorization fixtures.
- **SC-010**: the fourth email-dimension request is rate-limited without an
  additional attempt; PostgreSQL arbitration tests pass.
