# Private Beta Identity Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close T049 and T062 by deploying the `private-beta-identity` increment to a persistent Railway/Neon/R2 preview with real Supabase and Resend adapters, then capture exact-manifest provider, release, smoke, and rollback evidence.

**Architecture:** Keep Next.js as the only public browser surface and FastAPI private on Railway. Refactor the identity persistence port from exposed in-memory dictionaries to behavioral repository methods so the same application flow can run against either deterministic memory or PostgreSQL. Use one durable SQLAlchemy job runtime with a PostgreSQL outbox and RQ/Redis transport. Build public GHCR images once, promote their immutable digests to four Railway services, and run provider and release evidence through the public BFF.

**Tech Stack:** Python 3.13, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic, PostgreSQL 17, Supabase Python SDK, Resend Python SDK, RQ/Redis, boto3/R2, OpenTelemetry OTLP, Sentry, Next.js 16, TypeScript 6, Vitest, Playwright, GitHub Actions, Railway CLI.

## Global Constraints

- Implement on a new `codex/` branch created from `001-foundation-runtime` after bringing this approved design and plan onto that branch.
- Keep `InMemoryIdentityStore`, `RecordingJobQueue`, fake identity, and recording email only for local development and tests. `preview` must fail startup if any of them would be selected.
- Provider calls must remain outside database transactions. Queue messages contain only execution UUID, attempt number, and correlation UUID.
- Do not expose Supabase or Resend credentials, provider sessions, full capture URLs, email addresses, webhook bodies, or product session tokens in browser JSON, logs, traces, Sentry, or evidence.
- Use the Supabase server-only `sb_secret_` key. Do not introduce a legacy `service_role` key.
- Until DNS is controlled, use `Umbral <onboarding@resend.dev>` and record that Resend only delivers to the account owner plus provider test addresses.
- The public repository allows Railway Hobby to pull public GHCR images. Do not require Railway Pro or private-registry credentials for this beta.
- T049 is complete only after real Supabase/Resend conformance passes. T062 is complete only after a real preview deploy and rollback of exact manifest digests passes.
- Do not change product behavior, identity rules, ranking, notifications, or the deferred production topology.

## File and Interface Map

| Area | Existing seam | Planned change |
| --- | --- | --- |
| Settings | `src/umbral/infrastructure/config/settings.py` | Add explicit beta access/provider settings and exact Railway private-host validation |
| Identity application | `src/umbral/application/identity/ports.py` and access/authorization/administration services | Replace dictionary-shaped `IdentityStore` with behavioral persistence methods; domain models stay unchanged |
| Identity persistence | `src/umbral/infrastructure/db/repositories/identity.py` | Make memory and SQLAlchemy stores conform to the same port, including transaction, locking, sessions, audit, and webhook dedupe |
| Providers | `src/umbral/infrastructure/identity/supabase.py`, `src/umbral/infrastructure/email/resend.py`, registry | Compose real SDK callables, revoke transient Supabase sessions, use official Resend webhook verification |
| Jobs | `src/umbral/infrastructure/db/repositories/jobs.py` and `src/umbral/application/jobs/service.py` | Add durable SQLAlchemy runtime over the existing repository and outbox |
| Processes | `src/umbral/workers/` | Replace placeholder RQ entrypoint; add always-on worker and finite `scheduler-once` command |
| Web boundary | `apps/web/src/proxy.ts` and email webhook route | Select `product_session` or `cloudflare` boundary by environment; forward all Svix headers and raw bytes |
| Storage/telemetry | S3 adapter and observability modules | Make provider refs restart-safe; initialize OTLP and Sentry in API/worker composition |
| Railway/release | Dockerfiles, `infra/railway/`, workflows, deploy scripts | Define service contracts, build public images once, switch `source.image` by digest, smoke, and rollback |
| Evidence | ADR 0002/0003, identity runbook, feature tasks | Record observed output and close T049/T062 only after remote success |

---

### Task 1: Establish the beta configuration and access contract

**Files:**

- Modify: `src/umbral/infrastructure/config/settings.py`
- Modify: `tests/fixtures/configuration_cases.json`
- Modify: `tests/unit/config/test_settings.py`
- Modify: `tests/integration/identity/test_environment_isolation.py`
- Modify: `tests/contract/test_environment_access.py`

- [ ] **Step 1: Add failing preview configuration cases**

Add accepted cases with:

```json
{
  "UMBRAL_ENV": "preview",
  "UMBRAL_ACCESS_MODE": "product_session",
  "UMBRAL_API_BASE_URL": "http://api.railway.internal:8000",
  "REDIS_URL": "redis://redis.railway.internal:6379/0",
  "IDENTITY_PROVIDER": "supabase",
  "SUPABASE_URL": "https://bpwgyvetbneghrtxcadm.supabase.co",
  "SUPABASE_SECRET_KEY": "sb_secret_test_value",
  "IDENTITY_ISSUER": "https://bpwgyvetbneghrtxcadm.supabase.co/auth/v1",
  "IDENTITY_CAPTURE_ORIGIN": "https://umbral-beta.up.railway.app",
  "EMAIL_PROVIDER": "resend",
  "RESEND_API_KEY": "re_test_value",
  "RESEND_FROM_EMAIL": "Umbral <onboarding@resend.dev>",
  "EMAIL_WEBHOOK_SECRET": "whsec_test_value"
}
```

Add rejected cases for fake providers in preview, missing `SUPABASE_SECRET_KEY`, non-`sb_secret_` key, missing Resend sender, arbitrary private API hostname, public `redis://`, insecure cookie, and `cloudflare` mode without an audience.

- [ ] **Step 2: Run the focused tests and observe failure**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/config/test_settings.py tests/integration/identity/test_environment_isolation.py tests/contract/test_environment_access.py -q
```

Expected: failures for unknown `UMBRAL_ACCESS_MODE`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `RESEND_FROM_EMAIL` plus the currently rejected Railway private URLs.

- [ ] **Step 3: Implement the minimal settings model**

Add these typed fields:

```python
access_mode: Literal["product_session", "cloudflare"] = Field(
    default="cloudflare", validation_alias="UMBRAL_ACCESS_MODE"
)
supabase_url: str | None = Field(default=None, validation_alias="SUPABASE_URL")
supabase_secret_key: str | None = Field(
    default=None, validation_alias="SUPABASE_SECRET_KEY"
)
resend_from_email: str | None = Field(
    default=None, validation_alias="RESEND_FROM_EMAIL"
)
```

For `preview`:

- accept `http://*.railway.internal` for `UMBRAL_API_BASE_URL`;
- accept `redis://*.railway.internal` for `REDIS_URL`;
- keep HTTPS/TLS mandatory for all public hosts;
- require real Supabase/Resend providers and their explicit credentials;
- require `UMBRAL_ACCESS_AUDIENCE` only in `cloudflare` mode;
- require `SESSION_SECURE=true` and `__Host-umbral_session`.

Keep production validation unchanged except for the explicit access-mode conditional.

- [ ] **Step 4: Re-run focused tests**

Run the Step 2 command.

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/umbral/infrastructure/config/settings.py tests/fixtures/configuration_cases.json tests/unit/config/test_settings.py tests/integration/identity/test_environment_isolation.py tests/contract/test_environment_access.py
git commit -m "feat: validate beta provider configuration"
```

### Task 2: Compose a real Supabase proof adapter

**Files:**

- Modify: `src/umbral/infrastructure/identity/supabase.py`
- Modify: `src/umbral/infrastructure/identity/registry.py`
- Modify: `src/umbral/application/identity/access.py`
- Modify: `tests/contract/test_identity_provider.py`
- Create: `tests/contract/test_supabase_adapter.py`
- Modify: `tests/integration/identity/test_provider_failures.py`

- [ ] **Step 1: Write failing SDK-boundary tests**

Use a fake client that exposes `auth.admin.generate_link`, `auth.verify_otp`, and `auth.admin.sign_out`. Assert:

- `generate_link` receives `type="magiclink"`, the normalized email, and the exact `/auth/capture` redirect;
- only `properties.hashed_token` becomes the capture query value;
- expiry is exactly 15 minutes from the injected UTC clock;
- `verify_otp` receives `type="magiclink"` and the token hash;
- subject, verified email, issuer, and access token map to `ProviderProof`;
- `sign_out(access_token, scope="global")` runs before any Umbral user/session mutation;
- a missing user, email, token, issuer mismatch, SDK error, or sign-out error fails closed.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_supabase_adapter.py tests/contract/test_identity_provider.py tests/integration/identity/test_provider_failures.py -q
```

Expected: tests fail because the registry does not create an SDK client and revocation is unused.

- [ ] **Step 3: Add a narrow SDK client wrapper**

Keep SDK types behind the adapter. Build the real client at composition:

```python
from supabase import Client, create_client

def build_supabase_client(*, url: str, secret_key: str) -> Client:
    return create_client(url, secret_key)
```

Map `client.auth.admin.generate_link` and `client.auth.verify_otp` into provider-neutral dictionaries inside `SupabaseIdentityAdapter`. Return the access token only as `ProviderProof.revocation_handle`.

- [ ] **Step 4: Revoke the transient provider session before local activation**

In `IdentityAccess.confirm_magic_link`, after proof validation and before the transaction that creates or updates Umbral identity:

```python
if proof.revocation_handle is not None:
    self.provider.revoke_provider_session(proof.revocation_handle)
```

If revocation raises, return the existing stable provider-unavailable failure and create no local link, user, role, or session.

- [ ] **Step 5: Make the registry fail closed**

When `IDENTITY_PROVIDER=supabase`, require `SUPABASE_URL` and `SUPABASE_SECRET_KEY` and inject the real client. Keep the fake provider path only for local/tests.

- [ ] **Step 6: Re-run tests and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_supabase_adapter.py tests/contract/test_identity_provider.py tests/integration/identity/test_provider_failures.py -q
git add src/umbral/infrastructure/identity/supabase.py src/umbral/infrastructure/identity/registry.py src/umbral/application/identity/access.py tests/contract/test_supabase_adapter.py tests/contract/test_identity_provider.py tests/integration/identity/test_provider_failures.py
git commit -m "feat: compose Supabase identity proof"
```

### Task 3: Compose Resend delivery and official webhook verification

**Files:**

- Modify: `src/umbral/infrastructure/email/resend.py`
- Modify: `src/umbral/infrastructure/identity/registry.py`
- Modify: `apps/web/src/app/api/webhooks/email/route.ts`
- Modify: `tests/contract/test_resend_adapter.py`
- Modify: `tests/integration/identity/test_email_webhooks.py`
- Create: `apps/web/src/app/api/webhooks/email/route.test.ts`

- [ ] **Step 1: Write failing delivery tests**

Assert the Resend SDK call contains:

```python
{
    "from": "Umbral <onboarding@resend.dev>",
    "to": ["owner@example.com"],
    "subject": "Tu enlace para ingresar a Umbral",
    "html": expected_html,
    "text": expected_text,
    "tags": [{"name": "attempt_id", "value": str(attempt_id)}],
}
```

Assert the SDK options are `{"idempotency_key": idempotency_key}` and neither open nor click tracking is enabled in provider configuration or message content.

- [ ] **Step 2: Write failing raw-webhook tests**

Generate a valid Svix signature over `svix-id + "." + svix-timestamp + "." + raw_body` using a `whsec_` test secret. Assert that:

- `resend.Webhooks.verify` receives the untouched decoded body string;
- headers are mapped as `id`, `timestamp`, and `signature`;
- nested Resend payload `data.email_id` maps to the internal `email_id`;
- stale, tampered, malformed, and missing-header payloads fail;
- the Next route forwards content type plus `svix-id`, `svix-timestamp`, and `svix-signature` without parsing the body.

- [ ] **Step 3: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_resend_adapter.py tests/integration/identity/test_email_webhooks.py -q
npm run test --workspace @umbral/web -- route.test.ts
```

Expected: failures because the adapter uses a custom incomplete HMAC, has no sender, and the web route drops Svix headers.

- [ ] **Step 4: Implement the SDK boundary**

At composition, set the Resend SDK API key once and inject:

```python
sender=lambda params, options: resend.Emails.send(params, options)
verifier=lambda options: resend.Webhooks.verify(options)
```

Keep the injected callables in tests. Pass `RESEND_FROM_EMAIL` explicitly. Convert only the closed event fields `id`, `type`, and `data.email_id` to the application mapping.

- [ ] **Step 5: Forward the exact webhook envelope**

Read `request.arrayBuffer()` once and copy only these allowlisted headers:

```typescript
const forwardedHeaders = new Headers({
  "content-type": request.headers.get("content-type") ?? "application/json",
  "svix-id": request.headers.get("svix-id") ?? "",
  "svix-timestamp": request.headers.get("svix-timestamp") ?? "",
  "svix-signature": request.headers.get("svix-signature") ?? "",
});
```

- [ ] **Step 6: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_resend_adapter.py tests/integration/identity/test_email_webhooks.py -q
npm run test --workspace @umbral/web -- route.test.ts
git add src/umbral/infrastructure/email/resend.py src/umbral/infrastructure/identity/registry.py apps/web/src/app/api/webhooks/email/route.ts apps/web/src/app/api/webhooks/email/route.test.ts tests/contract/test_resend_adapter.py tests/integration/identity/test_email_webhooks.py
git commit -m "feat: integrate Resend delivery and webhooks"
```

### Task 4: Deepen the identity persistence port without changing domain rules

**Files:**

- Modify: `src/umbral/application/identity/ports.py`
- Modify: `src/umbral/application/identity/access.py`
- Modify: `src/umbral/application/identity/authorization.py`
- Modify: `src/umbral/application/identity/administration.py`
- Modify: `src/umbral/infrastructure/db/repositories/identity.py`
- Create: `tests/contract/test_identity_store.py`
- Modify: existing `tests/unit/identity/` and `tests/integration/identity/` callers as required

- [ ] **Step 1: Add one behavioral conformance suite**

Parameterize the suite initially with `InMemoryIdentityStore`. Cover save/load and transitions for invitations, users, links, roles, requests, attempts, sessions, append-only audit, provider-event dedupe, and rollback.

The application port must expose methods in this shape:

```python
class IdentityStore(Protocol):
    def transaction(self) -> ContextManager[None]:
        raise NotImplementedError
    def fingerprint(self, value: str) -> bytes:
        raise NotImplementedError
    def invitation_for_email(self, email: str) -> Invitation | None:
        raise NotImplementedError
    def save_invitation(self, invitation: Invitation) -> None:
        raise NotImplementedError
    def user(self, user_id: UUID) -> ProductUser | None:
        raise NotImplementedError
    def user_for_email(self, email: str) -> ProductUser | None:
        raise NotImplementedError
    def save_user(self, user: ProductUser) -> None:
        raise NotImplementedError
    def link_for_subject(
        self, provider: str, issuer: str, subject: str
    ) -> ExternalIdentityLink | None:
        raise NotImplementedError
    def save_link(self, link: ExternalIdentityLink) -> None:
        raise NotImplementedError
    def active_roles(self, user_id: UUID) -> set[str]:
        raise NotImplementedError
    def active_role(
        self, user_id: UUID, role: str
    ) -> RoleAssignment | None:
        raise NotImplementedError
    def has_active_administrator(self) -> bool:
        raise NotImplementedError
    def save_role(self, role: RoleAssignment) -> None:
        raise NotImplementedError
    def save_request(self, request: MagicLinkRequest) -> None:
        raise NotImplementedError
    def request(self, request_id: UUID) -> MagicLinkRequest | None:
        raise NotImplementedError
    def recent_requests(
        self, fingerprint: bytes, *, now: datetime, field: str
    ) -> int:
        raise NotImplementedError
    def save_attempt(self, attempt: MagicLinkAttempt) -> None:
        raise NotImplementedError
    def attempt(self, attempt_id: UUID) -> MagicLinkAttempt | None:
        raise NotImplementedError
    def attempt_for_provider_message(
        self, message_id: str
    ) -> MagicLinkAttempt | None:
        raise NotImplementedError
    def current_attempt(
        self,
        *,
        invitation_id: UUID | None = None,
        product_user_id: UUID | None = None,
    ) -> MagicLinkAttempt | None:
        raise NotImplementedError
    def session_by_digest(self, digest: bytes) -> ProductSession | None:
        raise NotImplementedError
    def save_session(self, session: ProductSession) -> None:
        raise NotImplementedError
    def claim_provider_event(self, provider: str, event_id: str) -> bool:
        raise NotImplementedError
    def append_audit(self, event: AccessAuditEvent) -> None:
        raise NotImplementedError
```

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_identity_store.py tests/unit/identity tests/integration/identity -q
```

Expected: the new contract fails because the store exposes mutable dictionaries instead of the behavioral methods.

- [ ] **Step 3: Implement the in-memory methods**

Retain dictionaries as private implementation details of `InMemoryIdentityStore`. Its `transaction()` keeps the existing re-entrant lock and deep-copy rollback behavior.

- [ ] **Step 4: Refactor application services to use only the port**

Replace every direct `store.invitations`, `users`, `links`, `roles`, `requests`, `attempts`, `sessions`, `audits`, and `lock` access. Preserve:

- neutral request responses and exact rate limits;
- provider calls outside transactions;
- single-use/supersession rules;
- seven-day idle expiry with activity timestamp updated only after an allowed protected action;
- atomic state plus audit changes;
- current-role and current-status authorization;
- webhook event idempotency.

- [ ] **Step 5: Prove there are no dictionary leaks**

```powershell
rg -n "store\.(invitations|users|links|roles|requests|attempts|sessions|audits|lock)" src/umbral/application/identity
```

Expected: no matches.

- [ ] **Step 6: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_identity_store.py tests/unit/identity tests/integration/identity -q
git add src/umbral/application/identity src/umbral/infrastructure/db/repositories/identity.py tests/contract/test_identity_store.py tests/unit/identity tests/integration/identity
git commit -m "refactor: deepen identity persistence port"
```

### Task 5: Implement PostgreSQL identity/session/audit persistence

**Files:**

- Modify: `src/umbral/infrastructure/db/repositories/identity.py`
- Modify: `src/umbral/infrastructure/db/models/identity.py` only if a missing uniqueness constraint is proven
- Modify: `src/umbral/ops/identity.py`
- Create: `tests/integration/identity/test_postgres_store_conformance.py`
- Modify: `tests/unit/identity/test_export.py`
- Modify: `tests/integration/identity/test_webhook_dedupe.py`
- Modify: `tests/integration/identity/test_magic_link_flow.py`

- [ ] **Step 1: Run the Task 4 contract against PostgreSQL**

Use the existing migrated PostgreSQL fixture and add `SqlAlchemyIdentityStore` as the second factory. Add restart tests that create state with one store/session factory and read it with another.

Also assert:

- concurrent rate-limit requests serialize on advisory locks;
- concurrent confirmation consumes one attempt once;
- `(provider, provider_event_id)` deduplicates across process instances;
- authorization activity and audit commit together;
- rollback leaves neither mutation nor audit row.
- the identity exit/export report can be rebuilt after a process restart without exposing email or bearer data.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/identity/test_postgres_store_conformance.py tests/integration/identity/test_webhook_dedupe.py tests/integration/identity/test_magic_link_flow.py -q
```

Expected: failures because `PostgresIdentityRepository` implements only a partial read seam.

- [ ] **Step 3: Implement domain-row mapping and transaction ownership**

Implement `SqlAlchemyIdentityStore(session_factory, fingerprint_key, environment)`. Each `transaction()` owns exactly one SQLAlchemy session and commits or rolls back once. Methods return domain dataclasses, while `save_*` methods upsert the corresponding ORM row inside the active transaction.

Use row locks for attempt/session state transitions and advisory transaction locks for email/origin limiter arbitration. Do not return ORM rows to the application.

- [ ] **Step 4: Persist webhook dedupe through the audit uniqueness constraint**

`claim_provider_event` must use the existing unique `(provider, provider_event_id)` database rule. Treat the unique conflict as an already-processed event; never keep a process-local set as preview truth.

- [ ] **Step 5: Make operator reporting work against PostgreSQL**

Replace the in-memory-only typing and dictionary iteration in `ops/identity.py` with read-only repository queries that return bounded counts plus stable user/provider/issuer/subject references. Keep normalized email, tokens, and provider-session handles out of the export.

- [ ] **Step 6: Re-run, migration-check, and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_identity_store.py tests/unit/identity/test_export.py tests/integration/identity/test_postgres_store_conformance.py tests/integration/identity/test_webhook_dedupe.py tests/integration/identity/test_magic_link_flow.py -q
.\scripts\check-migrations.ps1
git add src/umbral/infrastructure/db/repositories/identity.py src/umbral/infrastructure/db/models/identity.py src/umbral/ops/identity.py tests/unit/identity/test_export.py tests/integration/identity/test_postgres_store_conformance.py tests/integration/identity/test_webhook_dedupe.py tests/integration/identity/test_magic_link_flow.py
git commit -m "feat: persist identity state in PostgreSQL"
```

### Task 6: Implement the durable SQLAlchemy job runtime

**Files:**

- Create: `src/umbral/infrastructure/jobs/runtime.py`
- Modify: `src/umbral/infrastructure/db/repositories/jobs.py`
- Modify: `src/umbral/application/jobs/ports.py` only for shared claim/outcome types
- Create: `tests/integration/jobs/test_sqlalchemy_runtime.py`
- Modify: `tests/integration/jobs/test_submission_idempotency.py`
- Modify: `tests/integration/jobs/test_outbox_recovery.py`
- Modify: `tests/integration/jobs/test_worker_recovery.py`
- Modify: `tests/integration/jobs/test_scheduler_overlap.py`

- [ ] **Step 1: Parameterize durable-job behavior**

Run submission idempotency, outbox recovery, retry/lease recovery, and scheduler overlap contracts against both `InMemoryJobRuntime` and a new `SqlAlchemyJobRuntime`.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/jobs -q
```

Expected: SQLAlchemy runtime cases fail because only repository primitives exist.

- [ ] **Step 3: Implement the runtime over existing repository operations**

`SqlAlchemyJobRuntime` owns a session factory and exposes:

```python
def submit(self, command: SubmitJob) -> JobSnapshot:
    raise NotImplementedError
def get(self, execution_id: UUID) -> JobSnapshot:
    raise NotImplementedError
def identity(self, execution_id: UUID) -> JobIdentity:
    raise NotImplementedError
def correlation_id(self, execution_id: UUID) -> UUID:
    raise NotImplementedError
def claim(
    self, *, execution_id: UUID, attempt_number: int, worker_id: str
) -> JobClaim | None:
    raise NotImplementedError
def record_outcome(
    self, claim: JobClaim, outcome: Mapping[str, object] | Exception
) -> JobSnapshot:
    raise NotImplementedError
def relay_due(self, *, limit: int = 100) -> RelayResult:
    raise NotImplementedError
def reap_expired(self, *, limit: int = 100) -> int:
    raise NotImplementedError
def schedule_tick(self) -> int:
    raise NotImplementedError
```

Catch the unique execution identity conflict by rolling back and loading the winner. Publish only through the outbox relay after the insert transaction commits. Preserve bounded retries and stable error codes.

- [ ] **Step 4: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/jobs -q
git add src/umbral/infrastructure/jobs/runtime.py src/umbral/infrastructure/db/repositories/jobs.py src/umbral/application/jobs/ports.py tests/integration/jobs
git commit -m "feat: add durable SQLAlchemy job runtime"
```

### Task 7: Replace worker and scheduler placeholders with real processes

**Files:**

- Create: `src/umbral/workers/composition.py`
- Modify: `src/umbral/workers/worker.py`
- Modify: `src/umbral/workers/scheduler.py`
- Modify: `src/umbral/workers/__main__.py`
- Modify: `tests/unit/workers/test_cli.py`
- Create: `tests/integration/jobs/test_rq_process.py`

- [ ] **Step 1: Write failing process tests**

Assert:

- `worker` builds an RQ worker using `JSONSerializer` and the `umbral` queue;
- `run_message` validates all UUIDs, checks correlation identity, claims once, executes only an explicitly registered handler, and records outcome;
- `scheduler-once` relays pending outbox, reaps expired leases, claims at most the due work limit, and exits zero;
- `scheduler-once` exits non-zero on a database/Redis failure;
- `scheduler` is rejected in preview so Railway never runs the infinite in-memory loop.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/workers/test_cli.py tests/integration/jobs/test_rq_process.py -q
```

Expected: failures because both commands currently return zero without work and `run_message` discards its arguments.

- [ ] **Step 3: Implement one composition root**

Build settings, session factory, SQL identity store, Supabase/Resend registry, Redis connection, `RQJobQueue`, `SqlAlchemyJobRuntime`, and the explicit identity registry in `workers/composition.py`. Initialize telemetry through the same settings used by the API.

- [ ] **Step 4: Implement finite cron behavior**

`scheduler-once` performs, in order:

1. reclaim expired outbox leases;
2. reap expired job leases;
3. schedule due jobs until no due row remains or the configured limit is reached;
4. publish due outbox rows;
5. run identity retention maintenance;
6. emit one bounded result and exit.

- [ ] **Step 5: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/workers/test_cli.py tests/integration/jobs/test_rq_process.py tests/integration/jobs -q
git add src/umbral/workers tests/unit/workers/test_cli.py tests/integration/jobs/test_rq_process.py
git commit -m "feat: run durable worker and cron processes"
```

### Task 8: Compose preview API with durable adapters

**Files:**

- Modify: `src/umbral/api/dependencies.py`
- Modify: `src/umbral/api/main.py`
- Create: `src/umbral/infrastructure/runtime/composition.py`
- Modify: `tests/unit/api/test_dependencies.py`
- Create: `tests/integration/runtime/test_preview_composition.py`

- [ ] **Step 1: Write failing composition tests**

For local settings, assert memory/recording adapters remain available. For preview settings with injected factories, assert the dependency graph contains:

- `SqlAlchemyIdentityStore`;
- `SqlAlchemyJobRuntime`;
- `RQJobQueue`;
- `S3ObjectStore`;
- `SupabaseIdentityAdapter`;
- `ResendEmailAdapter`.

Assert preview startup fails if a fake, recording, memory, or filesystem adapter is selected.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/api/test_dependencies.py tests/integration/runtime/test_preview_composition.py -q
```

Expected: preview graph contains `InMemoryIdentityStore`, `InMemoryJobRuntime`, and `RecordingJobQueue`.

- [ ] **Step 3: Extract environment composition**

Keep `build_runtime_dependencies` as the API-facing entrypoint, but delegate concrete adapter selection to `infrastructure/runtime/composition.py`. Type `RuntimeDependencies` against ports rather than concrete in-memory classes.

- [ ] **Step 4: Add critical readiness probes**

Critical preview probes: PostgreSQL query and Alembic revision, required extensions, Redis ping, and R2 stat/write conformance marker. Supabase/Resend remain non-critical login capability probes. A failed critical dependency returns not-ready; provider failure returns degraded without invalidating existing product sessions.

- [ ] **Step 5: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/api/test_dependencies.py tests/integration/runtime/test_preview_composition.py tests/unit/identity tests/integration/identity -q
git add src/umbral/api/dependencies.py src/umbral/api/main.py src/umbral/infrastructure/runtime/composition.py tests/unit/api/test_dependencies.py tests/integration/runtime/test_preview_composition.py
git commit -m "feat: compose durable preview runtime"
```

### Task 9: Make object references restart-safe and initialize observability

**Files:**

- Modify: `src/umbral/infrastructure/object_store/s3.py`
- Modify: `src/umbral/infrastructure/object_store/factory.py`
- Create: `src/umbral/infrastructure/observability/runtime.py`
- Modify: `src/umbral/infrastructure/observability/otel.py`
- Modify: `src/umbral/infrastructure/observability/sentry.py`
- Modify: `src/umbral/api/main.py`
- Modify: `src/umbral/workers/composition.py`
- Modify: `tests/integration/object_store/test_s3_conformance.py`
- Create: `tests/contract/test_observability_composition.py`

- [ ] **Step 1: Add restart and redaction tests**

Write an S3 object with one adapter instance, reconstruct another instance, and assert `stat/open` work with the persisted `ProviderObjectRef`. Assert an unknown/malformed ref is rejected.

For observability, inject exporters and assert resource attributes contain only service, environment, release, and digest; Sentry has `send_default_pii=False` and the recursive filter; exporter failure does not change product results.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/object_store/test_s3_conformance.py tests/contract/test_observability_composition.py tests/contract/test_operational_signals.py -q
```

Expected: restart test fails because S3 refs depend on process-local dictionaries; observability composition test fails because providers are never initialized.

- [ ] **Step 3: Use a durable adapter reference**

Make `ProviderObjectRef.value` the validated storage key for S3. Its `repr` remains opaque, it contains no credentials/bucket name, and `_key_for_ref` validates the key before use. Remove process-local token maps from the S3 adapter.

- [ ] **Step 4: Initialize OTLP and Sentry once per process**

Configure OTLP HTTP exporters from `OTEL_EXPORTER_OTLP_ENDPOINT` and standard OTLP header environment variables. Set resource attributes from the bounded release settings. Call `initialize_sentry` and the OTLP initializer in both API and worker composition.

- [ ] **Step 5: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/object_store/test_s3_conformance.py tests/contract/test_observability_composition.py tests/contract/test_operational_signals.py tests/unit/identity/test_redaction.py -q
git add src/umbral/infrastructure/object_store src/umbral/infrastructure/observability src/umbral/api/main.py src/umbral/workers/composition.py tests/integration/object_store/test_s3_conformance.py tests/contract/test_observability_composition.py
git commit -m "feat: make storage and telemetry preview-ready"
```

### Task 10: Select the beta web access boundary

**Files:**

- Modify: `apps/web/src/proxy.ts`
- Modify: `apps/web/src/lib/access/cloudflare.ts`
- Create: `apps/web/src/lib/access/policy.ts`
- Create: `apps/web/src/lib/access/policy.test.ts`
- Modify: `infra/cloudflare/access-policy.json`
- Modify: `scripts/deploy/verify-access.ps1`
- Modify: `tests/contract/test_environment_access.py`

- [ ] **Step 1: Write failing policy tests**

Assert:

- `UMBRAL_ACCESS_MODE=product_session` bypasses Cloudflare JWT but does not create a product session;
- `cloudflare` mode keeps current JWT verification;
- public anonymous paths are exactly health, login, capture/confirm, neutral magic-link request, and email webhook;
- protected product routes remain subject to the existing Umbral session layout;
- unknown access mode fails closed;
- API remains private regardless of web access mode.

- [ ] **Step 2: Run and observe failure**

```powershell
npm run test --workspace @umbral/web -- policy.test.ts
.venv\Scripts\python.exe -m pytest tests/contract/test_environment_access.py -q
```

Expected: the blanket Cloudflare gate rejects beta login/capture/webhook paths.

- [ ] **Step 3: Implement the mode selector**

`proxy.ts` reads `UMBRAL_ACCESS_MODE`. In `product_session` mode it allows the request to reach public routes and the protected Next layout; it does not treat a missing Umbral cookie as an environment-gate concern. In `cloudflare` mode it preserves the current JWT behavior.

- [ ] **Step 4: Update the static access contract**

Make `verify-access.ps1` validate the selected mode plus the exact public path allowlist. For beta it must assert:

- web public domain exists;
- API has no public domain;
- datastores use private/external managed endpoints;
- product session protection remains enabled;
- webhook path is anonymous only at the environment gate.

- [ ] **Step 5: Re-run and commit**

```powershell
npm run test --workspace @umbral/web -- policy.test.ts route.test.ts
.venv\Scripts\python.exe -m pytest tests/contract/test_environment_access.py -q
git add apps/web/src/proxy.ts apps/web/src/lib/access infra/cloudflare/access-policy.json scripts/deploy/verify-access.ps1 tests/contract/test_environment_access.py
git commit -m "feat: support beta product-session access mode"
```

### Task 11: Define deployable containers and Railway service contracts

**Files:**

- Modify: `Dockerfile.runtime`
- Modify: `apps/web/Dockerfile`
- Create: `infra/railway/services.json`
- Create: `infra/railway/variables.example.json`
- Create: `scripts/deploy/validate-railway-config.ps1`
- Create: `tests/contract/test_railway_configuration.py`
- Modify: `tests/contract/test_release_manifest.py`
- Modify: `docs/architecture/decisions/0002-runtime-platform.md`

- [ ] **Step 1: Write failing static deployment tests**

Assert `services.json` defines:

| Service | Image | Start command | Exposure | Restart |
| --- | --- | --- | --- | --- |
| `web` | manifest web digest | image default | public, `/health` | on failure |
| `api` | manifest runtime digest | `python -m uvicorn umbral.api.main:app --host 0.0.0.0 --port 8000` | private only, `/health` | on failure |
| `worker` | manifest runtime digest | `python -m umbral.workers worker` | private only | always |
| `scheduler` | manifest runtime digest | `python -m umbral.workers scheduler-once` | cron, no public domain | never |

Assert scheduler cadence is at least five minutes, web/API serverless sleep is enabled, worker sleep is disabled, and all runtime services use the same runtime digest.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_railway_configuration.py tests/contract/test_release_manifest.py -q
```

Expected: missing Railway service contract and runtime container cannot start the API through an explicit command contract.

- [ ] **Step 3: Make the runtime image multi-process**

Retain one runtime image with Python environment, source, and Alembic assets. Remove the worker-only `ENTRYPOINT` and set a harmless default `CMD ["python", "-m", "umbral.workers", "--help"]` so Railway service commands select API, worker, or cron without rebuilding.

- [ ] **Step 4: Add non-secret variable inventory**

`variables.example.json` lists required variable names and service scopes only. It must not contain usable values. Separate:

- web: private API URL, BFF token, access mode, cookie settings, release identity;
- API: pooled database URL, Redis URL, R2 primary credentials, providers, telemetry, release identity;
- worker/cron: API runtime settings plus provider secrets and no public-origin credentials;
- release workflow: direct Neon URL, R2 recovery credentials, Railway project token, Sentry/Grafana probe identifiers.

- [ ] **Step 5: Record the beta-only platform exception**

Update ADR 0002 to retain Render/Cloudflare as the deferred production decision while documenting Railway/Neon/R2 as the approved preview exception, its USD 20 ceiling, lack of custom DNS, and exit conditions.

- [ ] **Step 6: Validate and commit**

```powershell
.\scripts\deploy\validate-railway-config.ps1 -ManifestPath tests\fixtures\release-manifests\valid.json
.venv\Scripts\python.exe -m pytest tests/contract/test_railway_configuration.py tests/contract/test_release_manifest.py -q
docker build --file Dockerfile.runtime --tag umbral-runtime:plan-check .
docker build --file apps/web/Dockerfile --tag umbral-web:plan-check .
git add Dockerfile.runtime apps/web/Dockerfile infra/railway scripts/deploy/validate-railway-config.ps1 tests/contract/test_railway_configuration.py tests/contract/test_release_manifest.py docs/architecture/decisions/0002-runtime-platform.md
git commit -m "build: define Railway beta services"
```

### Task 12: Build immutable public images and promote exact digests

**Files:**

- Modify: `.github/workflows/release.yml`
- Modify: `.github/workflows/promote.yml`
- Modify: `scripts/deploy/build-release.ps1`
- Create: `scripts/deploy/set-railway-images.ps1`
- Create: `scripts/deploy/wait-railway-services.ps1`
- Modify: `scripts/deploy/promote-release.ps1`
- Modify: `tests/unit/ops/test_release_ops.py`
- Modify: `tests/integration/delivery/test_release_flow.py`

- [ ] **Step 1: Write failing promotion tests with a fake Railway CLI**

Assert promotion:

- validates the manifest schema/checksum;
- forms each image reference by concatenating its manifest image name, `@`, and exact manifest digest;
- updates `source.image` for web, API, worker, and scheduler through a pinned Railway CLI;
- assigns one runtime digest to API/worker/scheduler;
- waits for successful deployment IDs and records them;
- never prints the Railway token or provider variables;
- aborts before image switching when access, backup, migration, or config gates fail.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/ops/test_release_ops.py tests/integration/delivery/test_release_flow.py -q
```

Expected: current scripts only write `deployed=false` and never operate Railway.

- [ ] **Step 3: Make the release workflow build and resolve digests once**

Use Docker Buildx to push public GHCR images tagged with the commit SHA. Resolve the registry digests after push and call `build-release.ps1` with those values. Upload the generated manifest and provenance as workflow artifacts.

- [ ] **Step 4: Implement the Railway image switch**

Pin `@railway/cli` in the workflow. For each service run the current CLI environment edit form:

```powershell
npx @railway/cli environment edit --environment preview --service-config $serviceName "source.image" $imageReference --message $releaseId --json
```

Then query deployment status in JSON until each required service is successful or the bounded timeout expires. Project tokens remain in GitHub environment secrets.

- [ ] **Step 5: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/ops/test_release_ops.py tests/integration/delivery/test_release_flow.py -q
git add .github/workflows/release.yml .github/workflows/promote.yml scripts/deploy/build-release.ps1 scripts/deploy/set-railway-images.ps1 scripts/deploy/wait-railway-services.ps1 scripts/deploy/promote-release.ps1 tests/unit/ops/test_release_ops.py tests/integration/delivery/test_release_flow.py
git commit -m "ci: promote immutable images to Railway"
```

### Task 13: Add Neon migration/backup and managed-dependency conformance gates

**Files:**

- Create: `src/umbral/ops/provider_conformance.py`
- Create: `scripts/deploy/backup-preview.ps1`
- Create: `scripts/deploy/migrate-preview.ps1`
- Create: `scripts/deploy/check-preview-dependencies.ps1`
- Create: `tests/contract/test_preview_dependency_gate.py`
- Create: `tests/integration/recovery/test_remote_backup_contract.py`
- Modify: `.github/workflows/promote.yml`

- [ ] **Step 1: Write failing gate tests**

With injected clients/command runner, require sanitized results for:

- PostgreSQL server major 17;
- Alembic current revision equals manifest revision;
- `postgis` and `vector` extensions exist;
- pooled URL is used by runtime and direct URL only by migration/backup jobs;
- Redis `PING` and enqueue/dequeue of an opaque test message;
- R2 primary write/stat/read and recovery-bucket copy;
- Grafana OTLP accepted signal;
- Sentry accepted sanitized event;
- Supabase issuer/reachability;
- Resend account/API reachability.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_preview_dependency_gate.py tests/integration/recovery/test_remote_backup_contract.py -q
```

Expected: missing remote gate and backup commands.

- [ ] **Step 3: Implement pre-migration backup**

`backup-preview.ps1` runs `pg_dump --format=custom` against `DATABASE_MIGRATION_URL`, computes SHA-256, uploads the dump and a redacted manifest to the R2 recovery bucket, then verifies object metadata. Evidence contains IDs, sizes, hashes, revision, and timestamps only.

- [ ] **Step 4: Implement migration and conformance**

`migrate-preview.ps1` verifies the backup evidence, runs `alembic upgrade head` with the direct URL, and checks the manifest revision plus extensions. `check-preview-dependencies.ps1` invokes the Python conformance module and writes a sanitized JSON result.

- [ ] **Step 5: Wire ordered promotion gates**

The workflow order is:

1. validate access/config;
2. create and verify backup;
3. migrate;
4. verify dependencies;
5. switch exact images;
6. run remote smoke.

- [ ] **Step 6: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_preview_dependency_gate.py tests/integration/recovery/test_remote_backup_contract.py tests/integration/recovery -q
git add src/umbral/ops/provider_conformance.py scripts/deploy/backup-preview.ps1 scripts/deploy/migrate-preview.ps1 scripts/deploy/check-preview-dependencies.ps1 tests/contract/test_preview_dependency_gate.py tests/integration/recovery/test_remote_backup_contract.py .github/workflows/promote.yml
git commit -m "feat: gate Neon and beta dependencies"
```

### Task 14: Replace the synthetic identity smoke with a real preview journey

**Files:**

- Modify: `src/umbral/ops/smoke.py`
- Modify: `src/umbral/ops/identity.py`
- Modify: `scripts/deploy/smoke.ps1`
- Modify: `scripts/deploy/smoke-identity.ps1`
- Create: `tests/integration/delivery/test_remote_smoke_contract.py`
- Modify: `tests/e2e/identity.spec.ts` only to share scenario data, not remote credentials

- [ ] **Step 1: Write a failing HTTP smoke contract**

Use a fake HTTP server and injected mailbox/provider observer. Assert the smoke:

- targets the manifest's public web origin only;
- verifies `/health`, `/ready`, and `/version` identity;
- preloads a dedicated invitation through an operator-only command, never a public API;
- requests a magic link through the BFF and observes a Resend message ID;
- extracts the provider token only inside the secure smoke process;
- verifies scanner prefetch does not consume it;
- explicitly confirms once and rejects reuse;
- verifies invited, repeat, and non-invited behavior;
- verifies current authorization, logout, and idle boundary;
- triggers delivered, bounced, and complained test events and verifies deduped audit projections;
- checks logs/evidence recursively for redaction canaries.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/delivery/test_remote_smoke_contract.py -q
```

Expected: current smoke always uses fake providers, in-memory state, and a recording queue.

- [ ] **Step 3: Implement explicit smoke modes**

Keep `run_identity_smoke()` as local synthetic coverage. Add `run_preview_identity_smoke(config)` that requires:

- public web base URL;
- exact release ID, manifest checksum, and digests;
- one dedicated invited test email;
- Resend API observation credential;
- operator command credential;
- bounded timeout.

It returns a structured result with scenario names, result codes, provider IDs, correlation IDs, timestamps, and durations, never emails or tokens.

- [ ] **Step 4: Add a non-interactive operator invitation command**

Add `python -m umbral.ops.identity preload-invitation`. It reads the invite address from the environment variable named by `--email-env`, uses the direct operator database URL from the environment variable named by `--database-url-env`, prints only the invitation UUID and result, and is exercised from the protected promotion workflow. It must never accept the email value as a command-line argument.

- [ ] **Step 5: Make PowerShell fail on any missing scenario**

`smoke.ps1` accepts `-Mode preview` and `-BaseUrl`. In preview mode it must not import fake or recording adapters. It verifies all four surfaces report the exact manifest before accepting the smoke.

- [ ] **Step 6: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/delivery/test_remote_smoke_contract.py tests/integration/identity tests/unit/identity -q
git add src/umbral/ops/smoke.py src/umbral/ops/identity.py scripts/deploy/smoke.ps1 scripts/deploy/smoke-identity.ps1 tests/integration/delivery/test_remote_smoke_contract.py tests/e2e/identity.spec.ts
git commit -m "feat: run real preview identity smoke"
```

### Task 15: Implement exact-manifest rollback

**Files:**

- Modify: `scripts/deploy/rollback.ps1`
- Create: `scripts/deploy/verify-schema-compatibility.ps1`
- Modify: `.github/workflows/promote.yml`
- Modify: `tests/integration/delivery/test_release_flow.py`
- Modify: `docs/runbooks/release-rollback.md`

- [ ] **Step 1: Add failing rollback tests**

Assert rollback:

- loads the previous valid manifest and its checksum;
- rejects a schema-incompatible previous revision before switching images;
- changes web and all runtime services back to their previous digests;
- waits for successful Railway deployments;
- runs the full preview smoke against the restored manifest;
- records elapsed seconds, deployment IDs, schema decision, smoke result, and `applied=true`;
- leaves database/product identity/audit data intact.

- [ ] **Step 2: Run and observe failure**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/delivery/test_release_flow.py -q
```

Expected: current rollback writes `applied=false` and changes nothing.

- [ ] **Step 3: Implement rollback by digest**

Reuse `set-railway-images.ps1` and `wait-railway-services.ps1` with the previous manifest. Run schema compatibility before the switch and remote smoke after it. If rollback smoke fails, report a failed rollback without deleting state or attempting a database downgrade.

- [ ] **Step 4: Re-run and commit**

```powershell
.venv\Scripts\python.exe -m pytest tests/integration/delivery/test_release_flow.py tests/unit/ops/test_release_ops.py -q
git add scripts/deploy/rollback.ps1 scripts/deploy/verify-schema-compatibility.ps1 .github/workflows/promote.yml tests/integration/delivery/test_release_flow.py docs/runbooks/release-rollback.md
git commit -m "feat: roll back Railway release by digest"
```

### Task 16: Run local full verification before provisioning

**Files:**

- Modify only failures attributable to Tasks 1-15
- Update generated: `contracts/openapi/v1/openapi.json`
- Update generated: `apps/web/src/lib/api/generated/index.ts`

- [ ] **Step 1: Regenerate and verify contracts**

```powershell
.\scripts\export-openapi.ps1
.\scripts\check-contracts.ps1
```

Expected: generated OpenAPI/client files match committed sources with no drift.

- [ ] **Step 2: Run focused provider/persistence/process suites**

```powershell
.venv\Scripts\python.exe -m pytest tests/contract/test_supabase_adapter.py tests/contract/test_resend_adapter.py tests/contract/test_identity_store.py tests/integration/identity tests/integration/jobs tests/integration/runtime tests/integration/delivery -q
```

Expected: all pass.

- [ ] **Step 3: Run web checks**

```powershell
npm run lint
npm run typecheck
npm run test
npm run build
```

Expected: all exit zero.

- [ ] **Step 4: Run the full project harness**

```powershell
.\scripts\check.ps1
```

Expected: harness reports no blocking failures.

- [ ] **Step 5: Scan for forbidden placeholders and secret-like values**

```powershell
rg -n "TO[D]O|FIX[M]E|pass$|service_role|SUPABASE_SERVICE_KEY|NEXT_PUBLIC_.*(SECRET|KEY)|onboarding@umbral\.com" src apps infra scripts .github tests docs
```

Expected: no implementation placeholders or prohibited secret/sender patterns; any intentional documentation match is reviewed and bounded.

- [ ] **Step 6: Commit generated verification changes**

```powershell
git add contracts/openapi/v1/openapi.json apps/web/src/lib/api/generated/index.ts
git commit -m "test: verify beta deployment runtime"
```

### Task 17: Provision the beta accounts and execute T049

**Operator prerequisites:**

- Railway Hobby workspace and empty `Umbral Beta` project;
- Neon Free PostgreSQL 17 project;
- Cloudflare account with two private R2 buckets;
- Grafana Cloud Free stack;
- Sentry Developer project;
- existing Supabase and Resend accounts;
- the Resend account-owner email selected as the invited smoke user.

- [ ] **Step 1: Provision external resources**

Create:

- Railway services `web`, `api`, `worker`, `scheduler`, and Redis;
- Neon database in the same practical region as Railway;
- R2 `umbral-preview-primary` and `umbral-preview-recovery` buckets with scoped tokens;
- Grafana OTLP token and endpoint;
- Sentry DSN with PII collection disabled.

Set Railway cost alert to USD 15 and hard limit to USD 20. Enable serverless sleep only for web/API. Keep the API without a public domain.

- [ ] **Step 2: Configure provider URLs**

After Railway generates the web domain:

- Supabase Site URL: exact generated origin;
- Supabase redirect: exact `/auth/capture` URL;
- Resend webhook: exact `/api/webhooks/email` URL;
- Resend sender: `Umbral <onboarding@resend.dev>`.

- [ ] **Step 3: Load sealed variables by service**

Generate unique BFF token and fingerprint key. Seal Supabase secret, Resend key/webhook secret, database URLs, Redis URL, R2 keys, Grafana token, Sentry DSN, and Railway tokens. Confirm the web service has no Supabase, Resend, R2, database, Redis, Grafana, or Sentry secret.

- [ ] **Step 4: Build a release and run provider conformance**

Trigger `release.yml` for the exact implementation commit, download the manifest, and run the ordered preview promotion through the dependency and provider-conformance gates.

- [ ] **Step 5: Capture SC-006 and SC-007 evidence**

Run:

```powershell
.\scripts\deploy\check-preview-dependencies.ps1 -ManifestPath artifacts\release-manifest.json -EvidencePath artifacts\t049-provider-conformance.json
.\scripts\deploy\smoke.ps1 -Mode preview -ManifestPath artifacts\release-manifest.json -BaseUrl $env:UMBRAL_PREVIEW_BASE_URL
```

Expected: real Supabase/Resend adapters pass redirect, expiry, issuer, invited/non-invited, delivery, outage, environment isolation, exit/export, and release gates.

- [ ] **Step 6: Attach evidence and close T049**

Update `docs/architecture/decisions/0003-identity-and-email-providers.md` with observed command, release ID, manifest checksum, scenario results, provider limits, date, and sanitized evidence path. Mark T049 complete only now.

- [ ] **Step 7: Commit T049 evidence**

```powershell
git add docs/architecture/decisions/0003-identity-and-email-providers.md specs/002-private-beta-identity/tasks.md
git commit -m "docs: record beta provider conformance"
```

### Task 18: Execute release, rollback, and close T062

- [ ] **Step 1: Promote the exact release manifest**

Run the GitHub `promote` workflow for `preview`. Confirm access, backup, migration, dependency, deployment, and remote smoke gates refer to the same manifest checksum and image digests.

- [ ] **Step 2: Exercise rollback**

Build a second harmless release whose schema remains backward compatible, promote it, then run:

```powershell
.\scripts\deploy\rollback.ps1 -PreviousManifestPath artifacts\previous-release-manifest.json -EvidencePath artifacts\t062-rollback.json
```

Expected: all four services return to the previous digests, remote smoke passes, `applied=true`, and identity/audit rows remain.

- [ ] **Step 3: Re-promote the accepted release**

Promote the intended final manifest again and run the full remote smoke. This leaves preview on the accepted release rather than the rollback target.

- [ ] **Step 4: Record SC-001 through SC-010**

Update `docs/runbooks/identity-access.md` with:

- exact release ID, commit, manifest checksum, and surface digests;
- sanitized results for all ten success criteria;
- provider/Neon/Railway/R2/Grafana/Sentry limits observed;
- Supabase Free pause recovery procedure;
- Resend DNS-free sender limitation;
- USD 15 alert and USD 20 hard-limit confirmation;
- rollback elapsed time and result;
- remaining custom-DNS and production-topology follow-ups.

- [ ] **Step 5: Close T062 and run the final harness**

Mark T062 complete, then run:

```powershell
.\scripts\check.ps1
git status --short
```

Expected: harness passes; only intended documentation/evidence/task changes are present.

- [ ] **Step 6: Commit final evidence**

```powershell
git add docs/runbooks/identity-access.md specs/002-private-beta-identity/tasks.md
git commit -m "docs: close private beta identity increment"
```

## Completion Gate

The increment is closed only when all conditions below are true:

- `preview` uses PostgreSQL identity/session/audit/job/schedule/outbox persistence;
- worker and cron execute real durable work;
- real Supabase generation/verification and transient-session revocation pass;
- real Resend delivery and official webhook verification pass;
- Railway public web/private API boundaries pass;
- Neon 17, PostGIS, pgvector, Redis recovery, R2, Grafana, and Sentry gates pass;
- one manifest's immutable digests identify web/API/worker/scheduler;
- rollback to a previous compatible manifest and re-promotion both pass;
- SC-001 through SC-010 evidence is sanitized and attached;
- T049 and T062 are checked;
- no custom DNS or production-readiness claim is made.
