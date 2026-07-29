# Quickstart: Foundation Runtime

This is the target operator/developer path for the implementation. It defines
the commands and observable finish line that implementation tasks must make
real; the current documentation-only repository does not provide them yet.

## Prepared Prerequisites

- Git
- Python `>=3.13,<3.14`
- [uv](https://docs.astral.sh/uv/) compatible with the checked lockfile
- Node.js `>=24.11,<25` and npm `>=12,<13`
- Docker Desktop with Compose
- PowerShell 7 or Windows PowerShell 5.1

The 15-minute acceptance clock starts after these prerequisites are installed,
with a clean checkout at the feature revision. It ends after all four surfaces
report the same release, all readiness states are `ready`, and the harness
passes.

## 1. Create Local Configuration

From `D:\Tomi\dev\umbral`:

```powershell
Copy-Item .env.example .env
Copy-Item apps\web\.env.example apps\web\.env.local
```

Local examples may contain dedicated non-production development credentials.
Preview and production must never accept the example values.

Minimum inventory:

| Value | Consumer | Local source | Secret | Rule |
| --- | --- | --- | ---: | --- |
| `UMBRAL_ENV` | all | `.env` | no | exactly `local` |
| `UMBRAL_RELEASE_ID` | all | generated dev value | no | nonempty bounded ID |
| `UMBRAL_RELEASE_MANIFEST` | all | local manifest path | no | schema-valid |
| `DATABASE_URL` | api/worker/scheduler | Compose | yes | PostgreSQL URL |
| `REDIS_URL` | api/worker/scheduler | Compose | yes | Redis URL |
| `OBJECT_STORE_BACKEND` | api/worker | `.env` | no | `filesystem` locally |
| `OBJECT_STORE_ROOT` | api/worker | `.env` | no | path inside repo-local data dir |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | all | local collector | no | local HTTP/gRPC endpoint |
| `SENTRY_DSN` | all | empty locally | yes | optional only in local |
| `UMBRAL_API_BASE_URL` | web server | `.env.local` | no | private/local API base |

The implemented inventory in `docs/runbooks/configuration.md` is
authoritative and also records owner, validation and permitted exposure for
every setting.

## 2. Install Locked Dependencies

```powershell
uv sync --all-groups
npm ci
```

`uv.lock` and `package-lock.json` are required. Do not resolve or upgrade
dependencies during a release build.

## 3. Start Local Dependencies and Migrate

```powershell
docker compose up -d postgres redis minio otel-collector
uv run alembic upgrade head
uv run alembic current --check-heads
```

The migration must verify `postgis` and `vector`. A missing extension or
unexpected Alembic head is a startup/readiness failure, not a warning.

## 4. Start the Four Surfaces

Open four terminals at the repository root.

API:

```powershell
uv run uvicorn umbral.api.main:app --reload
```

Worker:

```powershell
uv run python -m umbral.workers worker
```

Scheduler:

```powershell
uv run python -m umbral.workers scheduler
```

Web:

```powershell
npm run dev
```

Expected local addresses:

- web: `http://127.0.0.1:3000`
- API: `http://127.0.0.1:8000`
- API contract: `http://127.0.0.1:8000/openapi.json`

## 5. Verify Probes and Release Identity

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod http://127.0.0.1:8000/version
Invoke-RestMethod http://127.0.0.1:3000/health
Invoke-RestMethod http://127.0.0.1:3000/ready
Invoke-RestMethod http://127.0.0.1:3000/version
```

`/health` returns exactly:

```json
{"status":"alive"}
```

API and web readiness must be `ready`. The API's restricted aggregate runtime
view must report fresh `ready` heartbeats for worker and scheduler. All version
responses must share `release_id` and `manifest_sha256`; the web image digest
may differ from the shared Python runtime image digest.

## 6. Run the Full Harness

```powershell
.\scripts\check.ps1
```

The completed harness must run, without silently skipping an implemented
surface:

- required documentation;
- direct and transitive architecture contracts;
- Ruff formatting/lint and mypy;
- Python unit, contract and integration tests;
- extension, Alembic upgrade/head/drift checks;
- OpenAPI deterministic export and breaking-change check;
- generated web-client drift check;
- ESLint, TypeScript, Vitest and Next production build;
- Playwright foundation smoke and accessibility checks;
- release-manifest schema validation.

## 7. Run Focused Acceptance Checks

Durable jobs:

```powershell
uv run pytest tests\integration\jobs -q
```

Object-store conformance:

```powershell
uv run pytest tests\contract\test_object_store.py -q
```

Migrations:

```powershell
uv run pytest tests\migrations -q
```

Operational metadata:

```powershell
uv run pytest tests\contract\test_operational_signals.py -q
```

Web and accessibility:

```powershell
npm run test
npm run test:e2e
```

The duplicate-job fixture submits one identity ten times, injects a duplicate
transport delivery and proves one execution, one terminal result and one
reference effect.

## 8. Exercise Failure States

Stop only Redis:

```powershell
docker compose stop redis
```

Within 60 seconds:

- API remains available but reports `degraded`;
- worker and scheduler report `not_ready`;
- web remains ready if its private API check succeeds;
- no other surface changes to not-ready solely because Redis stopped.

Restart Redis:

```powershell
docker compose start redis
```

The outbox relay must reconstruct pending transport messages and every affected
surface must return to `ready` without duplicating the reference effect.

Repeat with MinIO/object storage. API becomes degraded, worker not ready,
scheduler remains ready, and unrelated health checks remain side-effect free.

## 9. Preview, Production and Recovery

Remote delivery is performed only through the protected release workflow:

1. select a schema-valid release manifest already proven in CI;
2. deploy its exact digests to persistent preview;
3. pass the Cloudflare/Render access gate, migration and smoke;
4. approve production promotion;
5. verify a recovery point newer than 12 hours;
6. deploy the same manifest, migrate and smoke;
7. attach evidence to the release.

Rollback starts when a smoke is declared failed and finishes only when the
previous manifest is `ready` on all surfaces and evidence is stored. Target:
15 minutes.

The implementation must provide:

- `docs/runbooks/release-rollback.md`;
- `docs/runbooks/backup-restore.md`;
- an initial and monthly restore drill;
- measured evidence that PostgreSQL plus objects restore into new namespaces
  within four hours and to a point no older than 24 hours.

Never run a restore over the damaged database or primary bucket. Restore
beside it, validate Alembic revision, record counts and object checksums, then
cut over and run smoke.

