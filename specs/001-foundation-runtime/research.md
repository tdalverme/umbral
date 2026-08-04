# Phase 0 Research: Foundation Runtime

**Date**: 2026-07-28  
**Scope**: UM-H1-001 a UM-H1-012 y UM-H1-016 a UM-H1-020  
**Status**: Complete; no `NEEDS CLARIFICATION` remains

## Decision Summary

| Area | Decision |
| --- | --- |
| Backend runtime | Python 3.13, synchronous FastAPI handlers, SQLAlchemy `Session` and Psycopg 3 |
| Dependency management | `pyproject.toml` plus exact `uv.lock`; `uv` is the only Python resolver |
| Database | Managed PostgreSQL 17 with PostGIS and pgvector; Alembic owns schema evolution |
| Jobs | RQ with JSON serialization over Redis; PostgreSQL owns execution state, retries, schedules and outbox |
| Object storage | S3-compatible `ObjectStore`; Cloudflare R2 remotely and filesystem locally |
| Web | npm workspace, Node.js 24 LTS, Next.js 16, React 19, TypeScript 6, Tailwind 4 and shadcn/ui |
| HTTP client | Checked-in OpenAPI 3.1 plus an exactly pinned Hey API generator and generated Fetch/TanStack client |
| Observability | Closed metadata allowlist, OpenTelemetry to Grafana Cloud, Sentry for errors/releases |
| Hosting | Render Pro, one persistent preview environment and one production environment |
| Temporary access | Cloudflare Access for operators and CI; only web `/health` may bypass Access |
| Delivery | Two OCI images built once, referenced by digest in one immutable release manifest |
| Recovery | Render PITR plus 12-hour encrypted logical DB dumps; immutable object replica and 35-day retention |

## 1. Synchronous Python Runtime

### Decision

Use Python `>=3.13,<3.14`. FastAPI route handlers, SQLAlchemy sessions, RQ
workers and object-store calls remain synchronous. Pin effective versions in
`uv.lock`; use compatible ranges in `pyproject.toml`.

Initial dependency bands:

| Dependency | Compatibility band |
| --- | --- |
| FastAPI | `>=0.138,<1` |
| Uvicorn | `uvicorn[standard]>=0.51,<1` |
| Pydantic | `>=2.13,<3` |
| pydantic-settings | `>=2.14,<3` |
| SQLAlchemy | `>=2.0.51,<2.1` |
| Alembic | `>=1.18,<2` |
| Psycopg | `psycopg[binary]>=3.3.4,<4` |
| GeoAlchemy2 | `>=0.20,<0.21` |
| pgvector Python | `>=0.5,<1` |
| RQ | `>=2.10,<3` |
| redis-py | `redis[hiredis]>=8,<9` |
| Boto3 | `>=1.43,<2` |

The implementation may raise patch floors when the lockfile is created, but
must not cross these major/minor compatibility boundaries without updating
this research decision.

### Rationale

The first runtime performs blocking database, Redis and S3-compatible calls.
A synchronous model keeps one concurrency model across HTTP, jobs and storage.
Python 3.13 is deliberately used instead of 3.14 because the selected RQ line
currently declares support through 3.13. SQLAlchemy requires one `Session` per
thread or execution attempt, which fits this model.

### Alternatives rejected

- **Async FastAPI plus `AsyncSession`**: valid if measured fan-out later
  justifies it, but it would mix blocking worker/storage libraries with an event
  loop before there is a concurrency need.
- **Python 3.14**: supported by FastAPI, SQLAlchemy and Psycopg, but not yet by
  every selected runtime dependency.
- **Poetry, pip-tools or multiple resolvers**: duplicate lock and environment
  policy without adding a required capability.

### Primary sources

- [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/)
- [SQLAlchemy session concurrency](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [SQLAlchemy 2.0 documentation](https://docs.sqlalchemy.org/en/20/)
- [Psycopg release notes](https://www.psycopg.org/psycopg3/docs/news.html)
- [uv installation and workflow](https://docs.astral.sh/uv/getting-started/installation/)

## 2. PostgreSQL, Transactions and Schema Evolution

### Decision

Use PostgreSQL 17 with `postgis` and `vector` extensions. Use `READ COMMITTED`
unless an individual use case demonstrates a stronger requirement. A
transaction manager owns commit, rollback and close; repositories may flush
but never commit.

Alembic has one linear head and:

- stable naming conventions for keys, checks and indexes;
- `compare_type=True` and `compare_server_default=True`;
- an initial migration that verifies or provisions `postgis` and `vector`;
- CI upgrades from empty and from the last released revision;
- `alembic current --check-heads` and `alembic check` drift gates;
- an explicit rollback or forward-compensation note in each revision.

Runtime processes never apply migrations on startup. A single pre-deploy
command applies them before a rollout.

### Rationale

PostgreSQL is the authoritative store for jobs and audit metadata as well as
future product records. Redis can therefore be lost and reconstructed.
PostgreSQL 17 is supported through 2029 and is mature across the chosen
extensions. Optimistic concurrency uses an integer `version` column and
SQLAlchemy's version counter; stale writes translate to a typed conflict.

### Alternatives rejected

- **SQLite in tests**: it cannot verify PostGIS, pgvector, PostgreSQL locking,
  constraints or migration behavior.
- **Migration on API boot**: multiple replicas could race and a failed
  migration would couple schema administration to traffic handling.
- **`updated_at` or PostgreSQL `xmin` as the public version**: the former is not
  a lock and the latter leaks storage internals.
- **PostgreSQL 18**: viable, but does not provide a needed V1 advantage over
  the more conservative supported baseline.

### Primary sources

- [PostgreSQL version policy](https://www.postgresql.org/support/versioning/)
- [PostgreSQL transaction isolation](https://www.postgresql.org/docs/17/transaction-iso.html)
- [SQLAlchemy version counters](https://docs.sqlalchemy.org/en/20/orm/versioning.html)
- [Alembic autogenerate and drift check](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [Render PostgreSQL extensions](https://render.com/docs/postgresql-extensions)

## 3. Durable Jobs and Simple Scheduling

### Decision

Use RQ as a thin Redis transport with `JSONSerializer`; messages contain only
an execution UUID and correlation metadata. PostgreSQL tables own job
identity, attempts, leases, terminal results, retry timing, schedules and a
transactional outbox.

Submission and execution follow this protocol:

1. Insert or load an execution under unique
   `(job_type, logical_target, idempotency_key)`.
2. Insert its outbox message in the same database transaction.
3. An outbox relay claims unpublished messages with a short lease and
   `FOR UPDATE SKIP LOCKED`, then publishes outside the transaction.
4. RQ uses deterministic transport ID `<execution_id>:<attempt_number>`.
5. A worker claims the execution in PostgreSQL before invoking its registered
   handler.
6. Terminal or actively leased duplicate deliveries are no-ops.
7. Explicit `TransientJobError` schedules bounded backoff; validation,
   invariant and unclassified errors are terminal.
8. A reaper recovers expired leases and the relay reconstructs lost Redis
   messages from PostgreSQL.

The default reference-job policy is five total attempts with delays of 30
seconds, 2 minutes, 10 minutes and 30 minutes plus bounded jitter. A job type
may declare a stricter policy. A deliberate rerun always uses a new
idempotency key.

The scheduler is an ordinary Python process. It claims due one-shot or
fixed-interval schedules in PostgreSQL, advances `next_run_at`, and creates the
execution and outbox atomically. An occurrence key is derived from schedule ID
and its planned UTC instant, so overlapping scheduler processes do not create
duplicate effects.

### Rationale

RQ has a small operational interface, Redis support, retries, timeouts,
scheduling primitives and a Windows-compatible worker option. Its own job
records and retries are not authoritative because they disappear with Redis.
The PostgreSQL outbox closes the database-to-queue loss window and makes
execution history auditable.

Delivery remains at-least-once. “One logical effect” is guaranteed by each
handler's transaction or external idempotency contract, not by claiming
impossible exactly-once message delivery.

### Alternatives rejected

- **Celery**: mature and appropriate for complex routing, canvas workflows or
  multiple brokers, but its larger operational surface is not needed here.
- **arq**: attractive for an async runtime, but its dependency ceiling is not
  aligned with the chosen Redis client/server baseline.
- **RQ CronScheduler as the source of schedules**: currently beta and stores
  scheduling truth in Redis.
- **Dramatiq**: also a sound small broker abstraction, but RQ's explicit job
  registry and current Windows worker story better match the selected
  synchronous bootstrap. Application semantics remain isolated behind
  `JobQueue`.

### Primary sources

- [RQ workers](https://python-rq.org/docs/workers/)
- [RQ retries](https://python-rq.org/docs/exceptions/)
- [RQ scheduling](https://python-rq.org/docs/scheduling/)
- [PostgreSQL `SKIP LOCKED`](https://www.postgresql.org/docs/17/sql-select.html)
- [Celery stable documentation](https://docs.celeryq.dev/en/stable/)

## 4. Versioned Object Storage

### Decision

Define a small application `ObjectStore` interface with `put_if_absent`,
`open` and `stat`. Implement:

- `FilesystemObjectStore` for local development and contract tests;
- `S3ObjectStore` using Boto3 for Cloudflare R2;
- the same conformance suite against filesystem and an S3-compatible MinIO
  test container.

The application generates immutable object and version IDs. A first write
creates an immutable key; retrying the same version and SHA-256 returns the
existing version; retrying it with different content is a conflict. Every read
verifies SHA-256. The database records the exact application version and remote
provider reference; callers never depend on “latest”, ETag semantics or bucket
listing.

A metadata state machine (`pending`, `available`, `failed`) makes the
database/object boundary recoverable. Upload goes to the immutable final key,
is verified, and only then becomes readable through metadata. A reconciler
finishes or marks stranded pending writes; readers only see `available`.

### Rationale

There are two real adapters, so this is a justified Seam. Application-level
version IDs and hashes keep correctness portable across S3-compatible
providers, whose conditional-write, ETag and versioning details differ.

### Alternatives rejected

- **Provider SDK in application/domain code**: leaks credentials and provider
  semantics across the architecture boundary.
- **Expose `list`, `delete`, signed URLs or buckets now**: no included story
  requires those operations.
- **Use the provider's “latest version”**: makes reproducibility and restore
  depend on mutable provider behavior.

### Primary sources

- [Boto3 `put_object`](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/put_object.html)
- [Amazon S3 checksum behavior](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html)
- [Cloudflare R2 bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/)

## 5. Web Runtime and Shared HTTP Contract

### Decision

Use a root npm workspace containing `apps/web`, with one `package-lock.json`
and root scripts that preserve `npm run dev` and `npm run build`.

Baseline:

| Dependency | Compatibility band |
| --- | --- |
| Node.js | `>=24.11,<25` |
| npm | `>=12,<13` with an exact `packageManager` |
| Next.js | `>=16.2,<17` |
| React / React DOM | `>=19.2,<20` |
| TypeScript | `>=6.0,<6.1` |
| ESLint | `>=10,<11` |
| Tailwind CSS | `>=4.3,<5` |
| TanStack Query | `>=5.101,<6` |
| Vitest | `>=5,<6` |
| Playwright | `>=1.61,<2` |

Initialize shadcn/ui with Base UI, the restrained Vega preset, CSS variables
and OKLCH semantic tokens. Add only button, field/input, card, alert, skeleton
and spinner primitives. Components use Server Components by default; `"use
client"` appears only where interaction requires it. Do not enable React
Compiler, Cache Components, Storybook or a shared UI package in this
increment.

FastAPI's deterministic OpenAPI 3.1 export is checked in at
`contracts/openapi/v1/openapi.json`. Pin `@hey-api/openapi-ts` exactly while it
is pre-1.0 and generate Fetch, TypeScript, SDK and TanStack Query output into a
fully generated directory. Every operation has an explicit stable
`operationId`.

Contract drift and compatibility are separate gates:

1. regenerate OpenAPI and compare it byte-for-byte;
2. regenerate the web client and require a clean Git diff;
3. run `oasdiff breaking` against the merge-base contract;
4. reject breaking changes in `v1`; an intentional break creates `/api/v2`
   and a `v2` contract.

### Rationale

The workspace keeps commands at repository root without prematurely creating
shared packages. Versioning generated output makes a stale consumer visible in
review and makes an offline build reproducible. A generated SDK avoids manual
DTOs while wrappers keep server/browser configuration out of generated code.

### Alternatives rejected

- **Vite SPA**: contradicts the accepted App Router ADR.
- **Manual DTOs or hand-written endpoint strings**: permit silent contract
  drift.
- **Regenerate only in CI and do not commit output**: local consumers may stay
  stale and builds become dependent on code generation availability.
- **Browser-to-private-API calls in this increment**: the API remains on
  Render's private network. The minimum page uses a server-side client; a BFF
  is introduced only when product identity or browser interaction requires it.

### Primary sources

- [Node.js release schedule](https://nodejs.org/en/about/previous-releases)
- [Next.js support policy](https://nextjs.org/support-policy)
- [Next.js App Router](https://nextjs.org/docs/app)
- [shadcn/ui Tailwind v4](https://ui.shadcn.com/docs/tailwind-v4)
- [Hey API configuration](https://heyapi.dev/docs/openapi/typescript/configuration)
- [FastAPI SDK generation](https://fastapi.tiangolo.com/advanced/generate-clients/)
- [oasdiff breaking-change rules](https://www.oasdiff.com/docs/breaking-changes)

## 6. HTTP, Correlation and Error Semantics

### Decision

Operational paths are unversioned and identical where a surface exposes HTTP:
`GET /health`, `GET /ready` and `GET /version`. Future product endpoints start
at `/api/v1`.

- `/health` checks only that the process can respond and has the exact minimal
  public body approved in the spec.
- `/ready` returns 200 for `ready` or `degraded`, 503 for `not_ready`.
  Promotion nevertheless accepts only `ready`.
- `/version` returns the release ID, manifest checksum, contract version,
  database revision and the current surface image digest.
- Only web `/health` is public. All other probes are private or Access
  protected.
- The API and web publish HTTP probes. Worker and scheduler publish bounded,
  allowlisted heartbeats; the API exposes their aggregated status privately.

Every request receives a server-generated UUID request ID. A valid incoming
UUID correlation ID is preserved; otherwise the server creates one. Both are
returned. OpenTelemetry manages W3C `traceparent` independently.

Errors use RFC 9457 `application/problem+json`, stable application error codes
and sanitized detail. Validation errors contain field paths and codes, never
the rejected values.

### Rationale

Process liveness must not depend on external systems. Readiness is operational
and detailed, so it must remain restricted. Separating request, correlation
and trace identities supports one request, a multi-step business flow and a
distributed trace without overloading one field.

### Primary sources

- [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
- [FastAPI error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/)

## 7. Readiness Matrix

### Decision

| Surface | Critical checks | Degradable checks |
| --- | --- | --- |
| web | valid runtime config; private API reachable | telemetry exporter |
| api | config; PostgreSQL; expected Alembic head; PostGIS; pgvector | Redis, object storage, telemetry exporter |
| worker | config; PostgreSQL; Redis; object storage; fresh execution loop | telemetry exporter |
| scheduler | config; PostgreSQL; Redis; fresh scheduling loop | telemetry exporter |

A critical failure makes only dependent surfaces `not_ready`. A degradable
failure leaves that surface able to serve its primary responsibility but
marks it `degraded`. Status must reflect a failure within 60 seconds. The
release gate requires all four surfaces `ready` and on the same release
manifest.

### Rationale

PostgreSQL plus the outbox allow the API to accept durable job submissions
while Redis is unavailable, so Redis is degradable for API but critical to the
worker and scheduler. Object operations are a capability of the API rather
than all API operations, so storage degradation does not withdraw unrelated
API behavior. Promotion remains stricter than runtime availability.

## 8. Closed-Field Observability

### Decision

Provide one safe telemetry facade for Python and one for TypeScript. Callers
choose a named operation and typed fields; they cannot attach arbitrary
dictionaries.

Allowed signal fields are:

- correlation ID and request ID;
- service/surface, environment and release;
- route template and HTTP method;
- operation, state/status and normalized error code;
- duration, retry/attempt number, job type/state and queue lag;
- object operation and content class, but never an object key.

Body, query string, path parameters, raw URL, header/cookie values, SQL
parameters, exception messages, credentials, free text and unclassified
attributes are dropped. Sentry default PII, replay and attachments are off;
`beforeSend` applies the same allowlist. Telemetry export failure is
non-fatal, increments a local failure signal and degrades readiness.

OpenTelemetry exports through a collector to Grafana Cloud. Sentry owns error
grouping, releases and alerts. Provider-native logs consume the same JSON
stdout output.

### Rationale

A central, closed interface is the test surface for the metadata-only policy.
Filtering after arbitrary payloads have already entered an SDK is an
insufficient primary control.

### Primary sources

- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [OpenTelemetry JavaScript](https://opentelemetry.io/docs/languages/js/)
- [Sentry data scrubbing](https://docs.sentry.io/security-legal-pii/scrubbing/)
- [Render logging](https://render.com/docs/logging)

## 9. Hosting and Temporary Access

### Decision

Use Render Pro with persistent `preview` and `production` projects in the same
chosen region:

- public Render Web Service for Next.js;
- private FastAPI service;
- two background-worker services for worker and scheduler;
- managed PostgreSQL 17;
- Render Key Value for Redis;
- private Cloudflare R2 primary and recovery buckets per environment.

Disable the Render `onrender.com` web subdomain and expose only a custom domain
proxied by Cloudflare. Cloudflare Access allows an operator email group and CI
service tokens. Next.js validates Access JWT signature, audience and
expiration, so reaching the origin without Access is still denied. Only
`/health` has a more-specific bypass policy.

The environment gate verifies:

- the Render origin subdomain is disabled;
- API and datastores have no public ingress;
- the Access application and audience match the environment;
- only `/health` has a bypass;
- CI tokens are scoped to that environment.

### Rationale

Render directly supports web, private service, workers, managed PostgreSQL,
Redis-compatible storage, private networking and prebuilt OCI images. Its
managed PostgreSQL supports PostGIS, pgvector and PITR. Cloudflare Access
supplies the explicitly required temporary environment control without
creating a Umbral user, session or role.

### Alternatives rejected

- **Railway Pro**: simple networking and preview environments, but its
  PostgreSQL is more self-managed and its integrated object buckets currently
  lack versioning, encryption and lifecycle/backup features required by this
  increment.
- **GCP Cloud Run/Cloud SQL/IAP**: stronger revision and access primitives, but
  materially more network/IaC work and a less natural continuously running
  worker baseline.
- **Render IP allowlists**: require a much more expensive workspace tier.
- **No public origin at all**: smallest attack surface, but does not exercise
  the approved access gate or give the persistent preview environment a usable
  operator entry point.

### Primary sources

- [Render private services](https://render.com/docs/private-services)
- [Render background workers](https://render.com/docs/background-workers)
- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Render prebuilt images](https://render.com/docs/deploying-an-image)
- [Cloudflare Access token validation](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/application-token/)
- [Cloudflare Access policy examples](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/common-policies/)

## 10. Immutable Promotion and Rollback

### Decision

GitHub Actions builds exactly two `linux/amd64` OCI images once:

- `umbral-web@sha256:<digest>`;
- `umbral-runtime@sha256:<digest>`, used by API, worker, scheduler, migrations,
  smoke and recovery commands.

A JSON release manifest binds both digests to Git SHA, build time, OpenAPI
major, Alembic head and configuration-schema version. Preview and production
receive the exact same manifest and digests; environment values are injected
at runtime. Mutable tags and environment-specific `NEXT_PUBLIC_*` builds are
forbidden.

Promotion order:

1. CI and image scan;
2. preview access gate;
3. preview migration, deploy and smoke;
4. explicit release-owner approval;
5. production access and fresh-backup gates;
6. production migration, deploy and smoke;
7. record deployment evidence and Sentry release.

Migrations are expand-first and keep the prior application compatible. Normal
rollback redeploys the prior manifest by digest without downgrading the
database. A data downgrade is used only when its migration declares and tests
that path; otherwise the approved forward compensation runs or promotion
stops.

### Rationale

One manifest represents the product version even though web and Python need
different images. Pinning digests prevents a mutable tag from changing during
promotion or rollback.

### Primary sources

- [Render deployment from prebuilt images](https://render.com/docs/deploying-an-image)
- [Render rollbacks](https://render.com/docs/rollbacks)
- [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)

## 11. Backup and Restore

### Decision

For production:

- use Render PostgreSQL PITR as the fast path;
- every 12 hours create an encrypted logical PostgreSQL dump in the recovery
  R2 bucket;
- every 12 hours copy new immutable object versions from the primary bucket to
  the recovery bucket and write a signed checksum manifest;
- apply R2 Bucket Lock and retain recovery artifacts for 35 days;
- perform the initial restore drill before release and repeat monthly;
- restore into new database/bucket namespaces, validate hashes, Alembic head
  and counts, then cut over and run smoke;
- budget 30 minutes decision, 120 minutes restore, 30 minutes validation and
  30 minutes cutover/smoke.

Redis is excluded because PostgreSQL outbox/schedules rebuild pending queue
state. Local and preview are reconstructed from migrations and fixtures.

### Rationale

The 12-hour cadence is stricter than the 24-hour RPO. Restoring beside the
damaged resource keeps validation reversible. The four-hour budget has 30
minutes of contingency and must be demonstrated rather than assumed from a
provider SLA.

### Primary sources

- [Render PostgreSQL recovery and backups](https://render.com/docs/postgresql-backups)
- [Cloudflare R2 bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/)
- [Cloudflare R2 durability](https://developers.cloudflare.com/r2/reference/durability/)

## 12. Verification Baseline

### Decision

Python uses Ruff, mypy, pytest and real PostgreSQL/Redis/MinIO integration
services. Web uses ESLint, `tsc --noEmit`, Vitest, Testing Library, Playwright
and axe. The architecture gate uses explicit dependency contracts in addition
to the existing lightweight import scan.

Minimum high-risk checks:

- invalid and unsafe configuration fixtures;
- direct and transitive forbidden imports;
- empty/previous migration, one head and no metadata drift;
- two stale optimistic updates;
- outbox publish interruption and Redis reconstruction;
- ten duplicate submissions, duplicate deliveries, expired lease and bounded
  retries;
- two scheduler processes claiming one occurrence;
- concurrent object put, hash mismatch and stranded-write reconciliation;
- deterministic OpenAPI, generated-client drift and breaking-change check;
- keyboard, both themes, contrast and axe on all foundation web routes;
- request/job/object correlation and allowlist rejection;
- critical dependency loss reflected within 60 seconds;
- same release manifest in four surfaces, smoke and timed rollback;
- timed database and object restore drill.

### Rationale

Tests target Interfaces and Seams rather than implementation internals. Real
service containers cover the PostgreSQL and S3-compatible behavior that local
substitutes cannot reproduce.

### Primary sources

- [Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing)
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- [Next.js testing guidance](https://nextjs.org/docs/app/guides/testing)

