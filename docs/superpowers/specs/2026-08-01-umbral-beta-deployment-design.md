# Umbral Beta Deployment Design

**Date**: 2026-08-01

**Status**: Approved

**Scope**: Persistent preview/private-beta deployment for the
`private-beta-identity` increment

**Budget ceiling**: USD 20 per month

## Amendment 2026-08-04: Railway-consolidated preview

The pipeline now uses a consolidated Railway topology: Railway provides
PostgreSQL (PostGIS/pgvector template, unmanaged) and Redis, and a single
S3-compatible object storage bucket; `NEON_DIRECT_URL`, the `DATABASE_MIGRATION_URL`
role split, `R2_RECOVERY_*`, and the two-bucket isolation/copy checks are
removed. Supabase Auth remains the only external identity provider and Resend
the transactional email provider, as decided in ADR 0003. Migration to Neon
later requires only changing `DATABASE_URL`. Cost ceiling and the other sections
below remain in effect unless contradicted here.

## Context

The foundation plan selected Render Pro, Cloudflare Access, Cloudflare R2,
Grafana Cloud, and Sentry as the eventual production topology. That topology
optimizes private networking, recovery, and operational guarantees, but its
required private service, workers, PostgreSQL, and Redis services do not fit a
USD 20 beta budget.

The beta can tolerate cold starts and low-volume service limits. It still needs
to exercise the real Umbral boundaries: a public Next.js BFF, private FastAPI,
PostgreSQL 17 with PostGIS and pgvector, Redis-backed jobs, an asynchronous
worker, scheduled maintenance, S3-compatible object storage, Supabase Auth,
Resend delivery, OpenTelemetry, Sentry, and an immutable release/rollback
workflow.

No custom DNS is currently available. The design therefore uses a provider
domain for beta and keeps custom-domain activation as a later operational
change.

## Decision

Use the following beta topology:

| Responsibility | Provider and plan | Runtime policy |
|---|---|---|
| Next.js web/BFF | Railway Hobby | Public Railway domain; serverless sleep enabled |
| FastAPI | Railway Hobby | Private Railway network only; serverless sleep enabled |
| Job worker | Railway Hobby | Always on with bounded resources |
| Scheduler and maintenance | Railway Cron | One-shot command, minimum five-minute cadence |
| Redis transport | Railway Redis-compatible service | Private network; disposable queue/cache state |
| Product PostgreSQL | Railway Postgres template, PostgreSQL 18 | Single private URL for runtime and migration; PostGIS/pgvector enabled |
| Object storage | Railway S3-compatible Object Storage | Single private bucket for objects and backups |
| External proof of email | Existing Supabase Free project | Auth only; no Umbral product tables |
| Transactional email | Existing Resend account | Resend test sender until DNS is controlled |
| Traces and metrics | Grafana Cloud Free | OTLP over HTTPS; metadata allowlist |
| Error monitoring | Sentry Developer | PII disabled; metadata allowlist |

Railway is the deployment control plane and private service network. Grafana,
Sentry, Supabase, and Resend are managed external dependencies; Umbral does not
run or patch their servers.

This decision replaces the Render/Cloudflare topology only for the beta
environment. It does not choose the final production platform. Production
promotion remains blocked until its topology, availability targets, backups,
and custom DNS are approved separately.

## Runtime Topology

The only public runtime is the Railway-provided web domain, for example
`https://umbral-beta.up.railway.app`. The browser communicates exclusively with
Next.js. Next.js performs server-side BFF calls to FastAPI through Railway's
encrypted private network at an environment-scoped `*.railway.internal` name.
FastAPI has no public Railway domain.

The data flow is:

1. A browser reaches the public Next.js login or product route.
2. Next.js validates the Umbral product session for protected routes.
3. Next.js forwards allowed server-side requests to private FastAPI with the
   environment-specific BFF credential and correlation ID.
4. FastAPI persists product truth in Railway PostgreSQL and publishes only opaque
   job references to Railway Redis.
5. The always-on worker consumes Redis jobs, reloads authoritative state from
   PostgreSQL, calls Supabase/Resend or other explicit adapters, and records the
   result transactionally.
6. Railway Cron starts bounded one-shot maintenance commands instead of
   deploying a permanent scheduler loop.
7. API, worker, and cron write objects through the S3-compatible port to the
   Railway object bucket and export allowlisted signals to Grafana Cloud and
   Sentry.

PostgreSQL remains authoritative for product identity, jobs, schedules,
outbox, audit, and recovery. Redis may be lost and rebuilt from PostgreSQL.
Supabase owns only external proof-of-email records; it never owns Umbral users,
roles, authorization, product sessions, or product tables.

## Network and Access Boundaries

### Public paths

The beta web origin exposes only the paths required by the product and provider
integration:

- `/health`;
- `/login` and the neutral magic-link request endpoint;
- `/auth/capture` and its explicit confirmation action;
- `/api/webhooks/email` for Resend, protected by raw-body signature validation;
- authenticated product routes guarded by the Umbral session.

Cloudflare Access is not used in beta because the project does not control DNS.
The current blanket Cloudflare JWT gate must be replaced by an environment-aware
boundary: Cloudflare remains supported for the future production topology, but
beta relies on Umbral identity plus Railway's private API network.

### Private API

The beta settings validator accepts an HTTP API origin only when its hostname
is exactly within the Railway private suffix and the environment is `preview`.
The Railway mesh encrypts service-to-service traffic. Public HTTP origins,
loopback addresses, arbitrary internal suffixes, and cross-environment service
names remain rejected.

Redis uses the Railway private connection string. A non-TLS `redis://` URL is
accepted in preview only for the exact Railway private hostname; any public or
non-Railway endpoint still requires `rediss://`.

### Webhook ingress

Resend calls `POST /api/webhooks/email` on the public Next.js domain. Next.js
must forward the untouched raw body and all required Svix headers to FastAPI.
FastAPI verifies the webhook with Resend's supported verification mechanism,
checks timestamp freshness, deduplicates the provider event ID, maps only the
closed event allowlist, and returns a neutral response. Cloudflare or Umbral
interactive login must never gate this path.

## DNS-Free Provider Testing

Until DNS for `umbral.com` is controlled:

- Supabase Site URL is the generated Railway web origin;
- Supabase permits the exact Railway `/auth/capture` redirect;
- Resend uses `Umbral <onboarding@resend.dev>`;
- real inbox delivery is limited to the email address that owns the Resend
  account;
- `delivered@resend.dev`, `bounced@resend.dev`, and
  `complained@resend.dev` exercise provider event and webhook paths;
- the Resend webhook points to the Railway web origin;
- `preview.umbral.com` and `identity@umbral.com` are not release claims.

After DNS access exists, the operator verifies a dedicated sending subdomain,
sets an environment-specific sender, adds the custom web domain, updates the
Supabase allowlist and Resend webhook atomically, runs provider conformance,
and removes the provider domain only after the custom-domain smoke passes.

## Configuration and Secrets

Railway variables are the beta secret store. Secret values are never committed,
printed in evidence, sent to the browser, or prefixed with `NEXT_PUBLIC_`.

The beta inventory adds explicit provider settings for:

- Supabase project URL;
- Supabase server-only `sb_secret_...` key;
- exact expected Supabase issuer;
- Resend API key;
- Resend webhook signing secret;
- Resend sender address;
- environment-specific BFF token and fingerprint key.

Legacy Supabase `service_role` credentials are not introduced. Supabase's
current `sb_secret_...` key is server-only and is injected only into FastAPI and
the worker. The web container receives neither Supabase secret nor Resend API
key. Next.js receives only its BFF credential and private API origin.

All beta secrets are distinct from local and future production values. The
startup validator rejects missing provider credentials, fake providers,
loopback redirects, insecure product cookies, shared example values, and
environment-crossover issuers/origins.

## Data Services

### Railway PostgreSQL

Create the Railway Postgres template with PostGIS and pgvector enabled through
Alembic/bootstrap verification. Runtime and release migrations share the same
single private connection string; no pooled/direct role split exists. The
service is unmanaged (no SLA/HA), which is acceptable for the private beta.

The database is expected to remain well below free/cheap storage allowances. A
usage alert at 70% of either limit triggers a move to a reviewed plan or a
migration; silent data deletion is never an acceptable response.

Preview composes the PostgreSQL identity, session, audit, job, schedule, and
outbox repositories. In-memory repositories remain limited to tests and local
development; they cannot satisfy preview persistence or release evidence.

### Railway Redis

Redis contains only disposable transport/cache state. The worker is always on,
uses native Redis protocol, and has conservative CPU/memory limits. PostgreSQL
outbox recovery reconstructs unpublished or lost queue messages after a Redis
restart.

### Railway Object Storage

Use one private S3-compatible bucket with no public listing. The S3 adapter
records checksums and provider references; release evidence tests write/read/stat
behavior against the single bucket and keeps backups under `backups/preview/`.
Credentials are scoped to the required bucket and operations. Custom DNS is not
required to use Railway object storage.

## Cost Controls

The Railway Hobby subscription is the only expected recurring paid component
during beta. Configure:

- a USD 15 compute alert;
- a USD 20 compute hard limit;
- per-service CPU and memory limits;
- serverless sleep on web and API;
- no serverless sleep on the worker;
- cron rather than a permanent scheduler process;
- private networking to avoid unnecessary egress.

Reaching the hard limit intentionally takes the beta offline. This is preferable
to unbounded spending during a test phase and must surface as an operational
alert. The first week of real usage is reviewed before invitations expand.

Grafana Cloud, Sentry, Supabase, and Resend remain on their free tiers
while within published limits. Approaching 70% of a hard provider quota creates
an operational follow-up before the quota is exhausted.

Expected low-volume cost is USD 5-15 per month. This is a planning estimate,
not a fixed price; the USD 20 Railway hard limit is the enforceable ceiling.

## Failure Behavior

- A sleeping web or API may add a cold start to the first request. The web shows
  a retryable neutral state and never interprets a timeout as an authorization
  decision.
- The worker remains available so an accepted magic-link request is not left
  waiting for an HTTP wake-up.
- PostgreSQL failure makes identity mutations and durable jobs
  unavailable; no product access is granted.
- Redis failure degrades job execution. PostgreSQL outbox state remains intact
  and is replayed after recovery.
- Supabase or Resend failure degrades login only and creates no user, external
  link, role, or session.
- A Supabase Free project can pause after sustained low activity and requires
  an operator resume; readiness and the runbook distinguish this from a normal
  application cold start.
- Object storage failure degrades object-dependent work without changing
  product truth.
- Grafana or Sentry failure is visible in readiness but never rolls back or
  changes a product transaction.
- A Railway hard-limit shutdown is an explicit beta outage, not a reason to
  bypass security or move secrets to another surface.

## Delivery, Verification, and Rollback

The deployment preserves the foundation's build-once rule:

1. CI builds the web and Python runtime OCI images once and records immutable
   digests in the release manifest.
2. The preview release gate validates Railway configuration, extensions
   and Alembic head, Redis, object storage, telemetry, provider isolation, and
   secret inventory without exposing values.
3. A release command runs backup evidence and forward migrations using the
   exact manifest.
4. Railway services deploy the recorded digests. Service-specific start
   commands select web, API, worker, or one-shot scheduler behavior without
   rebuilding.
5. Smoke executes the real public BFF/private API flow, provider conformance,
   webhook delivery/bounce/complaint paths, scanner prefetch, non-invited
   denial, session rules, authorization, redaction canaries, and readiness.
6. Promotion records the manifest and evidence only after all gates pass.
7. Rollback redeploys the previous image digests, verifies schema compatibility,
   re-runs smoke, and records elapsed time and result.

Provider conformance must use actual Supabase and Resend adapters. The current
fake/recording smoke cannot satisfy T049 or T062. The release evidence records
the DNS-free Resend limitation explicitly and does not claim delivery from
`@umbral.com`.

## Required Implementation Changes

The implementation plan must cover only the seams required by this deployment:

1. real Supabase and Resend HTTP/SDK composition behind existing ports;
2. official webhook signature verification and sender configuration;
3. settings support for provider URLs/keys and exact Railway private ingress;
4. beta web access policy without a blanket Cloudflare JWT requirement;
5. Railway service/build configuration for web, API, worker, and cron;
6. PostgreSQL composition for identity, sessions, audit, jobs, schedules, and
   outbox in preview, with in-memory adapters restricted to local/tests;
7. a real always-on worker entry point and finite cron entry point;
8. migration/readiness conformance for PostgreSQL (PostGIS and pgvector) and
   the single private URL;
9. Railway Redis and object storage integration conformance;
10. Grafana/Sentry beta configuration and redaction verification;
11. exact-manifest deploy, smoke, evidence, and rollback automation;
12. updates to the foundation platform ADR and identity runbook reflecting the
    beta-only exception to Render/Cloudflare.

No product feature, domain refactor, ranking change, notification expansion, or
production topology redesign is part of this work.

## Alternatives Considered

### All services on Railway

This minimizes accounts but makes PostgreSQL extensions, backups, and database
operation more self-managed. Persistent PostgreSQL, Redis, and worker resources
also put the USD 20 ceiling at risk. The 2026-08-04 amendment adopted this
option with a single bucket and unmanaged PostgreSQL; it was selected over the
alternatives below for the private beta.

### Maximum-free split across Vercel, Render, Neon, Upstash, and R2

This can approach USD 0 but exposes more public seams, fragments configuration,
and lacks a reliable free background worker. It increases operational work and
does not preserve the private BFF-to-API boundary cleanly.

### Original Render Pro and Cloudflare topology

This remains the stronger production candidate. Its private service, two
workers, managed PostgreSQL, and Redis baseline exceeds the beta budget. It is
deferred rather than rejected for production.

## Exit Criteria

The beta deployment design is complete when:

- the public Railway web origin and private FastAPI boundary are verified;
- the exact release manifest can deploy and roll back without rebuilding;
- Supabase/Resend provider conformance passes within the DNS-free limitations;
- Supabase Free pause detection and documented manual recovery are verified;
- PostgreSQL, PostGIS, pgvector, Redis recovery, object storage, Grafana, and
  Sentry checks pass;
- identity SC-001 through SC-010 evidence is attached to the accepted ADR and
  runbook;
- no secret or bearer material appears in source, logs, traces, Sentry,
  artifacts, or evidence;
- the Railway hard limit is USD 20 and the first-week projected cost stays at
  or below that ceiling;
- remaining production and custom-DNS work is listed as operational follow-up,
  not represented as completed.

## Current Provider References

- [Railway pricing](https://docs.railway.com/pricing)
- [Railway private networking](https://docs.railway.com/private-networking)
- [Railway serverless](https://docs.railway.com/deployments/serverless)
- [Railway cron jobs](https://docs.railway.com/cron-jobs)
- [Railway cost controls](https://docs.railway.com/pricing/cost-control)
- [Neon pricing](https://neon.com/pricing)
- [Neon PostgreSQL compatibility](https://neon.com/docs/reference/compatibility)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Grafana Cloud pricing](https://grafana.com/pricing/)
- [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys)
- [Resend test email addresses](https://resend.com/docs/dashboard/emails/send-test-emails)
