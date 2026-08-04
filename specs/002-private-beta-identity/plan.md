# Implementation Plan: Private Beta Identity

**Branch**: `002-private-beta-identity` | **Date**: 2026-07-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`/specs/002-private-beta-identity/spec.md`

## Summary

Implement the private-beta access gate defined by UM-H1-023 and UM-H1-013
through UM-H1-015. Invited people request a neutral, rate-limited magic-link
flow, activate exactly one Umbral product user, and receive an opaque Umbral
session that expires only after seven consecutive days without a valid
protected operation. Every protected operation re-evaluates current user
status, explicit role permission, and ownership; missing rules deny by default.

The design keeps product identity inside one deep `IdentityAccess` module.
PostgreSQL is authoritative for invitations, users, external links, roles,
sessions, link attempts, rate-limit evidence, and access audit. Supabase Auth
is selected only as an external proof-of-email Adapter and Resend only as an
email-delivery Adapter. Neither provider owns product sessions or
authorization. FastAPI remains private behind the Next.js BFF. A deliberate
confirmation step prevents email scanners from consuming links on `GET`.

## Technical Context

**Language/Version**: Python `>=3.13,<3.14`; TypeScript `>=6.0,<6.1`; Node.js
`>=24.11,<25`, inherited from `foundation-runtime`

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy 2, Alembic, Psycopg 3,
the foundation transaction/job runtime, official pinned Supabase Python client,
official pinned Resend Python client; Next.js 16, React 19, shadcn/ui, Tailwind
4, generated Hey API client

**Storage**: PostgreSQL 17 for all durable identity and access truth; Redis only
for disposable foundation job transport; provider-side Supabase Auth records
are external identity evidence, not product truth

**Testing**: pytest, pytest-asyncio, Testcontainers/PostgreSQL, provider fakes
and contract/conformance tests, migration and architecture checks; Vitest,
Testing Library, Playwright, axe, OpenAPI drift and `oasdiff`

**Target Platform**: Linux containers on the accepted Render/Cloudflare
topology; current evergreen browsers; local Docker Compose with fake/local
Adapters and Mailpit

**Project Type**: Modular-monolith Product API plus one Next.js BFF/web
application

**Performance Goals**: Public request acknowledgement p95 under 500 ms without
waiting for either external provider; issue an accepted email job within 30
seconds under beta load; validate and authorize an ordinary protected request
p95 under 150 ms excluding product work; complete 95% of 20 representative
first-access runs in under three minutes

**Constraints**: Link lifetime at most 15 minutes; one valid consumption;
latest issued link wins; exact rolling limits of 3/email and 20/origin in 15
minutes; seven-day idle session with no absolute lifetime; no token, full link,
credential, email body, raw origin, or unnecessary PII in telemetry/audit;
private FastAPI ingress; no open registration; fail closed on unknown rules,
conflicts, stale sessions, provider ambiguity, or audit failure

**Scale/Scope**: Controlled private beta, tens to low hundreds of invited
people, three fixed roles, one email identity per person, one web application,
two production providers, local fakes, and no invitation console, MFA, account
merge, or product-notification system

## Assumptions, Alternatives, and Tradeoffs

- `foundation-runtime` is implemented first and supplies configuration,
  transactions, job/outbox transport, correlation, deterministic OpenAPI,
  observability filtering, deployment, and recovery primitives. This increment
  extends those modules; it does not recreate them.
- Email normalization is intentionally conservative: trim surrounding ASCII
  whitespace, parse and validate as an email address, lowercase the domain, and
  lowercase the local part for this closed cohort. No provider-specific dot or
  plus folding occurs. Preload, request, and external-link checks use the same
  versioned rule.
- A public request is acknowledged before provider work. Eligible requests
  create a durable issue job by reference; ineligible and rate-limited requests
  create no provider call. This avoids membership leaks from provider latency
  and keeps raw email out of queue payloads.
- Link material is never persisted by Umbral. Once an issue worker starts an
  external call it is not automatically replayed after an ambiguous timeout or
  crash. The attempt becomes safely failed and the person requests a new link.
  This trades automatic recovery for eliminating durable bearer secrets and
  duplicate sends.
- The product session is an opaque, hashed, database-backed token instead of a
  Supabase browser session. This adds one indexed database lookup per protected
  operation but gives Umbral immediate status/role changes, exact idle expiry,
  revocation, and a provider exit path.
- UUID identity follows the foundation convention despite UUIDv4 index
  locality costs. Beta scale does not justify a new UUIDv7 extension or a
  cross-cutting identity migration.
- Product authorization remains in FastAPI/application code. The database is
  private and is not exposed through Supabase Data API, so RLS is defense not
  the primary authorization mechanism. Least-privilege database grants and
  architecture tests prevent browser/provider access to product tables.
- The first administrator is bootstrapped only for an already activated user,
  through a one-time environment-gated, audited operation that is valid only
  while no administrator exists. Every later privileged role change requires
  a current active administrator.

## Constitution Check

*GATE: Passed before Phase 0 research and re-checked after Phase 1 design.*

- **Persistent radar truth — PASS**: invitations, users, external identity
  links, role assignments, product sessions, attempts, and access decisions are
  persistent product objects. Provider sessions never replace them.
- **Auditable matching — PASS / N/A**: no scoring or LLM path is introduced.
  Authentication and authorization decisions are deterministic, versioned,
  finite, and tested through explicit interfaces.
- **Layer boundaries — PASS**: UI calls private Product API through the BFF;
  application modules own access workflows; domain values/policies import no
  FastAPI, SQLAlchemy, Supabase, Resend, worker, or UI code; infrastructure
  Adapters satisfy the two true-external seams.
- **Data lineage and evidence — PASS / N/A for Bronze/Silver/Gold**: this
  increment does not transform listing data. Access mutations and decisions
  preserve actor/source/correlation, stable reason, environment, and internal
  references without recording bearer material.
- **Minimal verifiable scope — PASS**: provider choice, auth flow, three roles,
  controlled preload/bootstrap, exact rate/session behavior, and audit are the
  minimum backlog scope. Invitation UI, MFA, social login, account recovery,
  support access, and product email remain deferred.

Post-design re-check: the BFF capture/confirm split, asynchronous issue job,
provider ports, and database-backed limiter are required by explicit
anti-prefetch, neutral-response, replaceability, exact-limit, and audit
requirements. No constitution violation requires an exception.

## Module and Seam Design

| Module | Interface used by callers/tests | Adapters / implementation | Behavior hidden behind the interface |
| --- | --- | --- | --- |
| `IdentityAccess` | `request_magic_link`, `confirm_magic_link`, `logout` | PostgreSQL repositories, foundation transaction/job runtime, identity-proof and email ports | normalization, eligibility, neutral response, latest-link state, activation transaction, conflict handling, session creation/revocation, audit |
| `AccessControl` | `authorize(session_token, action, resource_owner_id)` | PostgreSQL session/user/role repositories and pure policy | idle expiry with database time, current status/roles, deny-by-default, ownership, session touch only on allowed protected operations, audit |
| `AccessAdministration` | `preload_invitation`, `set_user_status`, `change_role`, `bootstrap_administrator` | PostgreSQL repositories and controlled CLI composition root | actor checks, uniqueness, privileged-role rules, first-admin guard, atomic audit |
| Identity-proof seam | `generate_magic_link`, `verify_magic_link`, `revoke_provider_session` | Supabase Auth Adapter and deterministic fake | provider credentials, request/response mapping, verified subject/email extraction, provider error normalization |
| Transactional-email seam | `send_magic_link`, `verify_webhook` | Resend Adapter and recording/Mailpit Adapter | provider payload, idempotency key, webhook signature and event mapping |
| `MagicLinkRequestLimiter` | `reserve(email_fingerprint, origin_fingerprint, now)` | PostgreSQL Adapter | exact rolling counts, transaction advisory locks, concurrent arbitration, 24-hour minimized evidence |

`IdentityAccess` is the external application seam and owns orchestration.
Provider ports are internal seams because production and local/test Adapters
both exist. HTTP routes, worker handlers, and CLI commands are composition
roots and contain no identity rules.

## Authentication and Session Flow

1. Next.js overwrites untrusted forwarding headers, computes an
   environment-scoped origin fingerprint from the trusted client address, and
   forwards the request to private FastAPI using internal BFF authentication.
2. FastAPI normalizes the email, reserves both rolling limits atomically, and
   records a minimized access request. If eligible, the same transaction
   creates a `pending` attempt and durable issue job containing only the
   attempt UUID. Every branch returns the same `202` body.
3. The issue worker claims the attempt once, reloads current eligibility and
   email from PostgreSQL, generates a 15-minute Supabase token, and sends the
   Umbral capture URL through Resend with idempotency key
   `identity.magic-link/{attempt_id}`. No external call runs inside a database
   transaction and link material is never stored.
4. After Resend accepts the message, a short transaction marks the attempt
   `issued` and all older unconsumed attempts for the same access subject
   `superseded`. An ambiguous provider result fails closed; it cannot grant a
   product session.
5. Email links target public `GET /auth/capture`. That route validates only
   shape/destination, stores attempt ID and token hash in a short-lived
   authenticated-encrypted `HttpOnly; Secure; SameSite=Strict` transient
   cookie, and redirects with `303` to clean `/auth/confirm`. It never verifies
   or consumes the token; edge/web logging for this route omits query strings.
6. The confirmation page requires an explicit user-initiated `POST`. The BFF
   sends the transient values server-to-server to FastAPI; the API first checks
   that the local attempt is current, issued, and unexpired, then asks Supabase
   to verify the proof.
7. Under one PostgreSQL transaction, Umbral re-checks eligibility and conflict
   rules, activates or resolves exactly one user/link, assigns only `user` on
   first activation, consumes the attempt, creates one opaque product session,
   and appends audit. Transport replay cannot create another session; if the
   first cookie response was lost, the consumed link returns a generic
   recoverable result instead of persisting or replaying the opaque token.
8. The BFF forwards the API `Set-Cookie` header as
   `__Host-umbral_session=<opaque>` with `Secure; HttpOnly; SameSite=Lax;
   Path=/` and no `Domain`. Local HTTP uses a separately named non-`__Host`
   cookie. Provider tokens are not returned to the browser and are revoked
   best-effort after proof extraction.
9. Each protected application operation locks and evaluates the session using
   PostgreSQL time, loads current user state and roles, applies an explicit
   action/ownership rule, and updates `last_activity_at` only if authorization
   succeeds. At exactly seven days idle, the operation expires the session
   instead of reviving it. Denied/public/background operations do not touch it.

## Authorization Design

Actions are stable strings registered in code. The policy accepts
`principal`, `action`, and an optional `resource_owner_id`; it returns an
allow/deny decision with a stable rule and reason. There is no wildcard fallback.

- `user`: allowed declared product actions only for self-owned resources.
- `operator`: allowed declared operational actions; no implicit user-content
  access and no privileged role grants.
- `administrator`: allowed identity status/role administration; no implicit
  user-content access.
- inactive user, unknown role/action, absent required owner, owner mismatch, or
  ambiguous resource: deny.

Later increments must add each new protected action to the finite matrix and
its cross-user fixtures before exposing the route. Not-found and not-owned
resources use the same external problem response whenever existence would be
sensitive.

## Data and Migration Design

The full schema and state machines are in [data-model.md](./data-model.md).
One Alembic revision adds:

1. `identity_invitations`;
2. `product_users`;
3. `external_identity_links`;
4. `role_assignments`;
5. `product_sessions`;
6. `magic_link_requests`;
7. `magic_link_attempts`;
8. `access_audit_events`.

Every foreign key is indexed, timestamps are `timestamptz`, states/roles use
bounded text plus named checks, and common filtered access paths use composite
or partial indexes. Mutable rows use foundation `RecordIdentity` versioning;
append-only audit/request evidence does not.

Concurrency uses transaction-scoped advisory locks in a documented order:
email fingerprint, origin fingerprint, access subject, invitation/user, then
attempt/session. External calls never hold locks. Unique constraints arbitrate
provider subject, product email, active role, session token hash, provider
event ID, and one product session per consumed attempt.

The application database remains private. If the selected Supabase project is
also provisioned with a database, Umbral creates no product tables there and
grants no Data API access. Supabase `service_role`/secret credentials exist only
in the FastAPI/worker environment.

## Provider and Environment Decision

Phase 0 selects Supabase Auth plus Resend. The comparison, current pricing,
risks, changelog notes, and exit plan are in [research.md](./research.md).
Implementation records the accepted decision as
`docs/architecture/decisions/0003-identity-and-email-providers.md`.

| Environment | Identity proof | Email | Allowed destinations |
| --- | --- | --- | --- |
| test | deterministic fake | recording fake | generated test domains only |
| local | local fake by default; Supabase local conformance profile optional | Mailpit/recording Adapter | loopback Umbral capture URLs |
| preview | isolated Supabase project | isolated Resend test/domain configuration | preview Umbral origin only |
| production | isolated Supabase project | verified production Resend domain | canonical production Umbral origin only |

Credentials, redirect allowlists, webhook secrets, fingerprint keys, and BFF
secrets are distinct per environment. No key is `NEXT_PUBLIC_*`. Provider
availability is not a readiness dependency for existing sessions; outage
degrades new login and emits a bounded operational signal.

## Contracts

- [OpenAPI auth contract](./contracts/openapi.yaml)
- [identity-provider seam and conformance](./contracts/identity-provider.md)
- [authorization actions and matrix](./contracts/authorization.md)
- [BFF, cookies, capture, and confirmation boundary](./contracts/web-auth-boundary.md)
- [access events and provider webhooks](./contracts/access-events.md)

Implementation merges the auth paths into deterministic
`contracts/openapi/v1/openapi.json` and regenerates the server-only web client.
Browser code never receives the private API host, provider secret, token hash,
or product session token through JSON. Recoverable link failures use RFC 9457
type/reason codes; the request endpoint always returns the neutral `202`.

## Observability, Audit, and Retention

Audit is append-only and written in the same transaction as every sensitive
state change. Authorization denials that make no product mutation still persist
a standalone audit transaction. If required audit cannot persist, the sensitive
operation fails closed.

Signals contain route templates, internal UUIDs, provider name, versioned event
type, result, stable reason, environment, and correlation IDs only. Query
strings, cookies, headers, emails, raw origins, provider payloads, exception
text, and request/response bodies are recursively filtered before logs, traces,
Sentry, or audit.

Email/origin HMAC fingerprints in `magic_link_requests` are retained for 24
hours, then purged by a registered foundation job. Attempt metadata follows the
approved security-audit retention policy; token material never enters it.
Resend delivery/bounce webhooks are signature-verified, deduplicated by provider
event ID, correlated to attempt via provider message ID, and translated to the
closed event allowlist.

## Delivery and Access Topology

FastAPI, PostgreSQL, Redis, and workers remain private. Production web becomes
public only at the Cloudflare proxy so invited users can reach login/capture;
product routes are protected by Umbral sessions. The Render origin stays
disabled. Web `/health`, login/request, capture, confirm, and static assets are
the only anonymous routes.

Preview may retain Cloudflare Access in addition to Umbral authentication for
team-only validation. Production removal of the temporary Cloudflare Access
email gate is a controlled release step after migration, provider conformance,
non-invited denial, scanner-prefetch, session, authorization, and rollback
smokes pass. This is the bounded exit from the temporary foundation posture.

## Project Structure

### Documentation (this feature)

```text
specs/002-private-beta-identity/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── openapi.yaml
│   ├── identity-provider.md
│   ├── authorization.md
│   ├── web-auth-boundary.md
│   └── access-events.md
├── checklists/
│   └── requirements.md
└── tasks.md                    # created later by /speckit-tasks
```

### Source Code (repository root)

```text
.
├── contracts/openapi/v1/openapi.json
├── src/umbral/
│   ├── domain/
│   │   └── identity/
│   │       ├── email.py
│   │       ├── models.py
│   │       ├── policy.py
│   │       └── events.py
│   ├── application/
│   │   └── identity/
│   │       ├── contracts.py
│   │       ├── ports.py
│   │       ├── access.py
│   │       ├── authorization.py
│   │       └── administration.py
│   ├── infrastructure/
│   │   ├── db/
│   │   │   ├── models/identity.py
│   │   │   └── repositories/identity.py
│   │   ├── identity/
│   │   │   ├── supabase.py
│   │   │   └── fake.py
│   │   └── email/
│   │       ├── resend.py
│   │       └── recording.py
│   ├── api/
│   │   ├── auth.py
│   │   └── routers/
│   │       ├── auth.py
│   │       └── email_webhooks.py
│   ├── workers/identity.py
│   └── ops/identity.py
├── alembic/versions/
├── apps/web/src/
│   ├── app/
│   │   ├── login/page.tsx
│   │   ├── auth/
│   │   │   ├── capture/route.ts
│   │   │   └── confirm/
│   │   │       ├── page.tsx
│   │   │       └── actions.ts
│   │   ├── api/
│   │   │   ├── auth/
│   │   │   │   ├── magic-link-requests/route.ts
│   │   │   │   ├── confirmations/route.ts
│   │   │   │   └── logout/route.ts
│   │   │   └── webhooks/email/route.ts
│   │   └── (protected)/layout.tsx
│   └── lib/
│       ├── api/server.ts
│       └── auth/
│           ├── cookies.ts
│           ├── origin.ts
│           └── server.ts
├── tests/
│   ├── unit/identity/
│   ├── architecture/test_identity_boundaries.py
│   ├── contract/
│   │   ├── test_identity_provider.py
│   │   ├── test_email_provider.py
│   │   └── test_auth_openapi.py
│   ├── integration/identity/
│   ├── migrations/test_identity_migration.py
│   └── e2e/identity.spec.ts
└── docs/
    ├── architecture/decisions/0003-identity-and-email-providers.md
    └── runbooks/identity-access.md
```

**Structure Decision**: extend the accepted modular monolith and single web
application. Identity domain values and pure policy live together; application
workflows present three small interfaces; provider and SQLAlchemy code stay in
infrastructure; routes, workers, and CLI commands are composition roots.
`apps/web` owns browser/BFF cookie handling but no product authorization.

## Planned Implementation Sequence

`/speckit-tasks` must split these phases into test-first, path-specific tasks
grouped by independently demonstrable user stories.

### Phase A — Provider Decision and Closed Contracts

- Record ADR 0003 from `research.md`, pin provider SDKs/lockfiles, define
  environment ownership, redirect allowlists, webhook secrets, disable
  click/open tracking, and document provider disable/exit procedures.
- Add the two provider ports, fakes, conformance suites, event allowlist,
  OpenAPI paths, and generated-client drift tests before production Adapters.
- Gate: fake plus optional local Supabase/Resend test profiles satisfy the same
  contract; no provider type crosses the application seam.

### Phase B — Persistent Identity and Controlled Administration

- Add migration tests, then identity tables, constraints, indexes, repositories,
  state machines, normalization, and append-only audit.
- Implement controlled invitation preload, status/role changes, and the
  zero-admin bootstrap guard through application interfaces and CLI.
- Gate: empty/previous migration, uniqueness/conflict, audit atomicity,
  cross-environment rejection, and privileged-role fixtures pass.

### Phase C — Neutral Request and Durable Issue Flow (US1)

- Test exact concurrent rolling limits, invited/uninvited timing/response
  equivalence, latest-link semantics, provider failures, issue-job duplicates,
  and minimized retention before implementation.
- Implement request reservation/eligibility/attempt/outbox transaction and the
  non-replayed worker issue state machine with Supabase and Resend Adapters.
- Gate: fourth/21st requests create zero issue jobs, provider calls, or
  invalidations; concurrent boundaries never exceed 3/20; provider outages
  create no access-granting partial state.

### Phase D — Safe Confirmation and Product Session (US1)

- Test scanner `GET` non-consumption, explicit `POST`, invalid/expired/
  superseded/reused links, activation rollback, identity conflicts, ten
  duplicate confirmations, cookie attributes, logout, and the exact idle edge.
- Implement capture/confirm BFF routes, provider proof validation, atomic
  activation or repeat login, opaque session cookie, logout, and seven-day
  database-time expiry.
- Gate: one invitation produces one user/link/default role/session; repeat
  login resolves the same user; all invalid variants fail safely; no bearer
  value appears in logs or bodies.

### Phase E — Deny-by-default Authorization (US2)

- Write the complete anonymous/user/operator/administrator/inactive by
  own/other/operational action matrix first.
- Implement pure policy plus transactional `AccessControl`, integrate the
  protected web layout and representative Product API routes, and require
  later routes to register actions.
- Gate: zero cross-user access; status/role removal affects the next operation;
  denied and background requests do not extend the session.

### Phase F — Provider Events, Operations, and Release (US3/US4)

- Verify Resend raw-body signatures, event deduplication, delivery/bounce audit,
  redaction canaries, retention purge, provider outage visibility, and degraded
  readiness behavior.
- Execute local, preview, and production provider conformance/smoke; transition
  the production web gate from Cloudflare Access to Umbral identity through the
  accepted manifest and rollback workflow.
- Gate: all SC-001 through SC-010 evidence, provider decision criteria, exact
  environment isolation, production non-invited denial, rollback, and full
  harness pass.

## Verification Commands

Target commands after implementation:

```powershell
uv sync --frozen --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests
uv run pytest tests/unit/identity tests/contract/test_identity_provider.py tests/contract/test_email_provider.py
uv run pytest tests/integration/identity tests/migrations/test_identity_migration.py
uv run alembic current --check-heads
uv run alembic check
npm ci
npm run lint
npm run typecheck
npm run test
npm run api:check
npm run build
npm run test:e2e -- identity.spec.ts
.\scripts\check.ps1
```

Provider/release evidence additionally executes isolated preview conformance,
email delivery/bounce, scanner-prefetch, non-invited denial, role/ownership,
idle-session, logout, exact rate-limit, rollback, and secret/redaction canaries
using the exact release manifest. A mock-only or dashboard-only check cannot
close UM-H1-023.

## Requirement Traceability

| Backlog / requirement | Plan ownership | Primary evidence |
| --- | --- | --- |
| UM-H1-023, FR-001–FR-003, SC-007 | provider decision, environment table, ADR 0003 | provider comparison and isolated preview/production conformance |
| UM-H1-013, FR-005–FR-013, FR-022, FR-027–FR-030 | `IdentityAccess`, limiter, issue/confirm state machines | neutral response, concurrent limits, scanner, duplicate, conflict and outage suites |
| UM-H1-014, FR-004, FR-009–FR-014, FR-019–FR-021 | product user/link/session and `AccessControl` | repeat identity, status freshness, logout and seven-day idle tests |
| UM-H1-015, FR-015–FR-018 | pure policy and controlled administration | finite role/ownership matrix and bootstrap/privileged-grant fixtures |
| FR-023–FR-026, SC-005–SC-006 | environment isolation, audit/event contract, redaction | cross-environment rejection, audit reconstruction and recursive canary scans |
| SC-001–SC-004, SC-008–SC-010 | end-to-end gates in Phases C–F | 20 beta journeys, rejection corpus, duplicates, stable identity, idle and limit boundaries |

## Complexity Tracking

No constitution violation is present. The asynchronous issue job, BFF
capture/confirm split, two provider ports, and database-backed product session
are the minimum mechanisms needed to satisfy neutral timing, scanner safety,
provider replaceability, exact idle revocation, and immediate authorization
freshness. Simpler rejected alternatives and their concrete failure modes are
recorded in [research.md](./research.md).
