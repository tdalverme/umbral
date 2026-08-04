# Tasks: Private Beta Identity

**Input**: Design documents from `/specs/002-private-beta-identity/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`, and the completed `foundation-runtime` increment.

**Organization**: Tasks are grouped by setup, blocking foundation, and the
four user stories from `spec.md`. Every behavioral slice has an executable
test or contract check before its implementation task.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Make the repository able to build the backend, web BFF, local
dependencies, migrations, generated client, and identity test fixtures.

- [x] T001 Add pinned `supabase` and `resend` backend dependencies, Python version bounds, and lockfile entries in `pyproject.toml` and `uv.lock`
- [x] T002 [P] Add the Next.js server-only identity dependencies, workspace scripts, and lockfile entries in `apps/web/package.json`, `package.json`, and `package-lock.json`
- [x] T003 [P] Add local Postgres, Redis, and Mailpit services plus non-secret identity/email settings in `compose.yaml` and `.env.example`
- [x] T004 [P] Create the planned identity module and test directories with package boundaries in `src/umbral/domain/identity/__init__.py`, `src/umbral/application/identity/__init__.py`, `src/umbral/infrastructure/identity/__init__.py`, `src/umbral/infrastructure/email/__init__.py`, `tests/unit/identity/__init__.py`, `tests/integration/identity/__init__.py`, `tests/contract/__init__.py`, `tests/migrations/__init__.py`, `tests/architecture/__init__.py`, and `tests/e2e/identity.spec.ts`
- [x] T005 [P] Configure identity pytest markers, async fixtures, architecture import rules, and web test scripts in `tests/conftest.py`, `pyproject.toml`, `.github/workflows/check.yml`, and `apps/web/package.json`
- [x] T006 Add deterministic OpenAPI export, server-only generated-client, drift, and breaking-change commands in `apps/web/openapi-ts.config.ts`, `contracts/openapi/v1/openapi.json`, `scripts/check-contracts.ps1`, and `apps/web/src/lib/api/generated/index.ts`

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Complete the seams and runtime capabilities that every story
depends on. No user-story implementation starts before this phase passes.

- [x] T007 [P] Write failing identity-provider and email-provider conformance tests for redirect allowlists, bounded expiry, stable subject/email proof, redacted errors, idempotency keys, and signed webhooks in `tests/contract/test_identity_provider.py` and `tests/contract/test_email_provider.py`
- [x] T008 [P] Write the failing structural auth-contract test for RFC 9457 problems, neutral `202`, confirmation `Set-Cookie`, session cookie security, and the five operations in `tests/contract/test_auth_openapi.py`
- [x] T009 [P] Write failing migration-harness tests for empty database, foundation-head upgrade, one Alembic head, and metadata drift in `tests/migrations/test_identity_migration_harness.py`
- [x] T010 Record the accepted Supabase Auth plus Resend decision, owners, environment matrix, redirect destinations, credential isolation, disable procedure, and provider exit plan in `docs/architecture/decisions/0003-identity-and-email-providers.md` and `docs/runbooks/identity-access.md`
- [x] T011 Implement the provider-independent identity contracts, DTOs, stable error taxonomy, and secret-bearing value wrappers in `src/umbral/application/identity/contracts.py` and `src/umbral/application/identity/ports.py`
- [x] T012 Implement strict per-environment settings validation for provider issuer, redirect origin, BFF credential, fingerprint keys, webhook secret, link/session durations, and production-safe cookie names in `src/umbral/infrastructure/config/settings.py`
- [x] T013 Implement deterministic identity, email, recording, and Mailpit test Adapters satisfying the provider contracts in `src/umbral/infrastructure/identity/fake.py` and `src/umbral/infrastructure/email/recording.py`
- [x] T014 Integrate identity transactions, foundation job/outbox submission, correlation propagation, and required audit writes with the existing runtime in `src/umbral/application/transactions.py`, `src/umbral/workers/registry.py`, `src/umbral/domain/audit.py`, and `src/umbral/infrastructure/db/transaction.py`
- [x] T015 Integrate trusted BFF authentication, correlation headers, private API routing, and server-only forwarding in `src/umbral/api/dependencies.py`, `src/umbral/api/middleware/correlation.py`, and `apps/web/src/lib/api/server.ts`
- [x] T016 Add the closed identity event/reason registry and recursive secret/PII redaction baseline to `src/umbral/domain/identity/events.py` and `src/umbral/infrastructure/observability/filtering.py`

**Checkpoint**: contracts, settings, fakes, transactions, jobs, correlation,
redaction, and provider decision are available; `tests/contract` and the
foundation checks can run before any external provider credential is configured.

## Phase 3: User Story 1 — Acceder a la beta por invitación (Priority: P1) 🎯 MVP

**Goal**: An invited person can request, explicitly confirm, and reuse a
magic-link login while an uninvited person never receives product access.

**Independent Test**: Preload one invitation, request and consume a valid link,
reach a protected surface, repeat access with the same external subject, and
verify that uninvited, invalid, replaced, disabled, logged-out, idle-expired,
duplicate, and rate-limited cases create no unauthorized session.

### Tests for User Story 1

- [x] T017 [P] [US1] Write failing unit tests for versioned email normalization, invitation eligibility, link state transitions, latest-issued-wins, and fifteen-minute expiry in `tests/unit/identity/test_email.py` and `tests/unit/identity/test_link_state.py`
- [x] T018 [P] [US1] Write failing concurrent limiter tests proving three requests per normalized email, twenty per origin, rolling fifteen-minute aging, and no invalidation on a rejected request in `tests/unit/identity/test_rate_limit.py`
- [x] T019 [P] [US1] Write failing HTTP contract tests for neutral magic-link request, confirmation recovery/denial problems, session lookup, logout, and cookie headers in `tests/contract/test_auth_endpoints.py`
- [x] T020 [P] [US1] Write failing PostgreSQL integration tests for invitation preload, first activation, repeat login, identity conflict, provider failure, atomic rollback, and ten duplicate confirmations in `tests/integration/identity/test_magic_link_flow.py`
- [x] T021 [P] [US1] Write failing migration fixtures for invitation/user/link/role/session/attempt/request tables and concurrent partial-index behavior in `tests/migrations/test_identity_migration.py`
- [x] T022 [P] [US1] Write failing Playwright scenarios for login, Mailpit link capture, scanner `GET` non-consumption, explicit confirmation `POST`, secure cookie, logout, and recoverable expired-link UI in `tests/e2e/identity.spec.ts`

### Implementation for User Story 1

- [x] T023 [US1] Implement pure normalized-email values, invitation/user/link/attempt/session values, and link/session state guards without framework imports in `src/umbral/domain/identity/email.py` and `src/umbral/domain/identity/models.py`
- [x] T024 [US1] Implement the identity Alembic revision, SQLAlchemy mappings, named checks, foreign-key indexes, current-state partial indexes, and least-privilege grants in `alembic/versions/002_private_beta_identity.py` and `src/umbral/infrastructure/db/models/identity.py`
- [x] T025 [US1] Implement PostgreSQL repositories and transaction-scoped email/origin limiter arbitration with database-time queries in `src/umbral/infrastructure/db/repositories/identity.py`
- [x] T026 [US1] Implement controlled invitation preload, default `user` assignment, zero-partial-conflict checks, and the audited CLI composition root in `src/umbral/application/identity/administration.py` and `src/umbral/ops/identity.py`
- [x] T027 [US1] Implement the Supabase admin link/proof Adapter, reject public signup paths, Resend HTTP Adapter, Mailpit Adapter wiring, provider issuer checks, fifteen-minute expiry, and no-click/open-tracking email template in `src/umbral/infrastructure/identity/supabase.py`, `src/umbral/infrastructure/email/resend.py`, and `src/umbral/infrastructure/email/recording.py`
- [x] T028 [US1] Implement `IdentityAccess.request_magic_link`, durable attempt creation, neutral response, one-claim issue worker, safe provider failure state, Resend idempotency key, and latest-issued-wins transaction in `src/umbral/application/identity/access.py` and `src/umbral/workers/identity.py`
- [x] T029 [US1] Implement `IdentityAccess.confirm_magic_link` and `logout` with pre-verification current-attempt checks, atomic activation/repeat-link transaction, external-subject conflict rejection, opaque SHA-256 session token, and seven-day idle fields in `src/umbral/application/identity/access.py`
- [x] T030 [US1] Implement private FastAPI request, confirmation, session, and logout routes with RFC 9457 mapping, neutral `202`, BFF authentication, and allowlisted `Set-Cookie` forwarding in `src/umbral/api/auth.py`, `src/umbral/api/routers/auth.py`, and `src/umbral/api/main.py`
- [x] T031 [US1] Implement the login page, authenticated-encrypted capture cookie, non-consuming capture route, explicit confirmation page/action, server-only BFF routes, cookie helpers, and generic recovery/error states in `apps/web/src/app/login/page.tsx`, `apps/web/src/app/auth/capture/route.ts`, `apps/web/src/app/auth/confirm/page.tsx`, `apps/web/src/app/auth/confirm/actions.ts`, `apps/web/src/app/api/auth/magic-link-requests/route.ts`, `apps/web/src/app/api/auth/confirmations/route.ts`, `apps/web/src/app/api/auth/logout/route.ts`, and `apps/web/src/lib/auth/cookies.ts`
- [x] T032 [US1] Wire the identity service dependencies, provider Adapters, issue job registration, session dependency, and local Mailpit configuration into `src/umbral/api/dependencies.py`, `src/umbral/workers/registry.py`, `apps/web/src/lib/auth/server.ts`, and `compose.yaml`
- [x] T033 [US1] Run the focused US1 unit, contract, migration, integration, and Playwright suite, record the ten acceptance scenarios and SC-001/SC-002/SC-004/SC-008/SC-009/SC-010 evidence in `specs/002-private-beta-identity/quickstart.md`, and fix only failures attributable to this story

**Checkpoint**: The invited first-access and repeat-access journey works end to
end with fakes/Mailpit, and all invalid, duplicate, idle, logout, and limit
cases fail closed without provider tokens in telemetry.

## Phase 4: User Story 2 — Mantener aislados usuarios y responsabilidades (Priority: P2)

**Goal**: Every protected operation uses current identity, status, explicit role,
and ownership; unknown rules deny by default.

**Independent Test**: Execute the finite anonymous/user/operator/administrator/
disabled matrix against own, foreign, missing, ambiguous, and operational
resources and observe only explicitly allowed outcomes.

### Tests for User Story 2

- [x] T034 [P] [US2] Write failing pure-policy tests for every registered action, role, owner condition, unknown role/action, and deny-by-default result in `tests/unit/identity/test_policy.py`
- [x] T035 [P] [US2] Write failing integration tests proving current status/role removal takes effect on an existing session, operators cannot read private content, administrators cannot use a wildcard, and denials do not touch activity in `tests/integration/identity/test_authorization_matrix.py`
- [x] T036 [P] [US2] Write failing architecture tests that reject FastAPI, SQLAlchemy, provider, worker, and UI imports from identity domain/policy modules in `tests/architecture/test_identity_boundaries.py`

### Implementation for User Story 2

- [x] T037 [US2] Implement the finite action registry, ownership requirements, role matrix, stable policy version, and pure deny-by-default evaluator in `src/umbral/domain/identity/policy.py`
- [x] T038 [US2] Implement `AccessControl.authorize` with current session/user/role loading, exact database-time idle boundary, allowed-operation activity touch, and authorization audit in `src/umbral/application/identity/authorization.py` and `src/umbral/infrastructure/db/repositories/identity.py`
- [x] T039 [US2] Implement audited user status changes, role grant/revoke, privileged-role checks, and one-time zero-administrator bootstrap in `src/umbral/application/identity/administration.py` and `src/umbral/ops/identity.py`
- [x] T040 [US2] Integrate the authorization dependency into protected FastAPI composition and the Next.js protected layout without protecting health/login/capture assets in `src/umbral/api/auth.py`, `src/umbral/api/dependencies.py`, `apps/web/src/app/(protected)/layout.tsx`, and `apps/web/src/lib/auth/server.ts`
- [x] T041 [US2] Run the full authorization matrix and architecture suite, record SC-003 and FR-014–FR-021 evidence in `specs/002-private-beta-identity/contracts/authorization.md`, and fix only story-specific failures

**Checkpoint**: A session never bypasses current status, role, or ownership;
all unregistered/ambiguous combinations deny and preserve the seven-day idle
semantics.

## Phase 5: User Story 3 — Elegir y operar proveedores reemplazables (Priority: P3)

**Goal**: Provider choices and environment operation remain documented,
isolated, observable, and replaceable while provider outages grant no access.

**Independent Test**: Validate the decision record against every required
criterion, run isolated preview/provider conformance, inject identity/email
outages, and verify zero product sessions/links/users are created partially.

### Tests for User Story 3

- [x] T042 [P] [US3] Write a failing decision-record checklist test covering magic links, independent FastAPI validation, previous-link invalidation, isolation, deliverability, cost, observability, local support, owners, and exit strategy in `tests/contract/test_provider_decision_record.py`
- [x] T043 [P] [US3] Write failing provider outage/rejection integration tests for identity generation, identity verification, email acceptance, timeout, and ambiguous provider results in `tests/integration/identity/test_provider_failures.py`
- [x] T044 [P] [US3] Write failing environment-isolation tests for issuer, redirect, BFF credential, webhook secret, fingerprint key, provider project, and production-cookie rejection in `tests/integration/identity/test_environment_isolation.py`

### Implementation for User Story 3

- [x] T045 [US3] Implement the provider registry, environment-scoped Adapter selection, controlled provider disablement, and stable identity export/exit command without changing Umbral user/role/ownership IDs in `src/umbral/application/identity/ports.py`, `src/umbral/infrastructure/config/settings.py`, and `src/umbral/ops/identity.py`
- [x] T046 [US3] Integrate identity/email dependency health as degraded login capability rather than product-session readiness, with bounded provider metrics and no sensitive dimensions in `src/umbral/application/runtime/readiness.py` and `src/umbral/infrastructure/observability/otel.py`
- [x] T047 [US3] Add isolated preview provider smoke/conformance execution for redirect, expiry, issuer, non-invited denial, delivery, outage, and exit evidence in `src/umbral/ops/smoke.py`, `scripts/deploy/smoke.ps1`, and `docs/runbooks/identity-access.md`
- [x] T048 [US3] Implement the controlled production transition from temporary Cloudflare Access product gating to Umbral session protection, including origin/private-ingress checks and rollback instructions in `infra/cloudflare/access-policy.json`, `scripts/deploy/verify-access.ps1`, and `docs/runbooks/identity-access.md`
- [ ] T049 [US3] Run the decision, outage, environment, provider-conformance, and release-gate checks and attach SC-006/SC-007 evidence to `docs/architecture/decisions/0003-identity-and-email-providers.md`

**Checkpoint**: Every environment has isolated provider configuration and
credentials; provider failures degrade login only, and replacement preserves
Umbral product identity and audit truth.

## Phase 6: User Story 4 — Reconstruir decisiones de acceso (Priority: P4)

**Goal**: Security/operations can reconstruct access decisions and delivery
outcomes from minimal correlated evidence without bearer material or unnecessary
PII.

**Independent Test**: Exercise request, issue, delivery, consume, expiry,
reuse, conflict, authorization, role/status, logout, and provider-failure
paths; reconstruct each result from event references and pass recursive
redaction checks.

### Tests for User Story 4

- [x] T050 [P] [US4] Write failing event-coverage tests for every closed authentication, authorization, role, status, session, conflict, and provider-delivery event in `tests/integration/identity/test_access_events.py`
- [x] T051 [P] [US4] Write failing recursive redaction tests for logs, traces, Sentry payloads, problem responses, audit fields, cookies, URLs, provider tokens, bodies, emails, and origins in `tests/unit/identity/test_redaction.py`
- [x] T052 [P] [US4] Write failing webhook integration tests for raw-body signature verification, stale/tampered rejection, provider-event deduplication, monotonic delivery projection, and unknown-event handling in `tests/integration/identity/test_email_webhooks.py`

### Implementation for User Story 4

- [x] T053 [US4] Implement the closed access-event registry, append-only repository inserts, provider-event uniqueness, audit atomicity, and bounded reason validation in `src/umbral/domain/identity/events.py` and `src/umbral/infrastructure/db/repositories/identity.py`
- [x] T054 [US4] Implement raw-body Resend webhook verification, allowlisted event mapping, internal attempt correlation, duplicate handling, and public BFF forwarding in `src/umbral/infrastructure/email/resend.py`, `src/umbral/api/routers/email_webhooks.py`, and `apps/web/src/app/api/webhooks/email/route.ts`
- [x] T055 [US4] Implement the 24-hour fingerprint purge and security-audit retention hooks without deleting required product identity history in `src/umbral/workers/identity.py`, `src/umbral/ops/identity.py`, and `docs/runbooks/identity-access.md`
- [x] T056 [US4] Add an operator reconstruction query/report using only internal references, stable reasons, policy versions, event IDs, and correlation IDs in `src/umbral/ops/identity.py` and `docs/runbooks/identity-access.md`
- [x] T057 [US4] Run event, webhook, redaction, retention, and failure-path checks and record SC-005 plus FR-024–FR-026 evidence in `specs/002-private-beta-identity/contracts/access-events.md`

**Checkpoint**: Critical access decisions are reconstructible and correlated;
recursive canaries find zero tokens, complete links, credentials, message
bodies, raw origins, or unnecessary PII.

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Close release, documentation, generated-contract, performance,
security, and full-harness evidence across all stories.

- [x] T058 [P] Regenerate `contracts/openapi/v1/openapi.json` and the server-only web client, then fail CI on uncommitted drift in `scripts/check-contracts.ps1`, `contracts/openapi/v1/openapi.json`, and `apps/web/src/lib/api/generated/index.ts`
- [x] T059 [P] Execute 20 representative first-access journeys, rejection corpus, duplicate confirmations, scanner prefetch, exact limits, idle boundary, and repeat-identity scenarios in `tests/e2e/identity.spec.ts`
- [x] T060 [P] Run every `quickstart.md` local validation step with fake providers/Mailpit and update only observed command/output corrections in `specs/002-private-beta-identity/quickstart.md`
- [x] T061 Run architecture, migration, contract, lint, typecheck, unit, integration, web, accessibility, build, and redaction checks through `.github/workflows/check.yml` and `scripts/check.ps1`
- [ ] T062 Run the final preview/release/rollback smoke against the exact release manifest and attach SC-001–SC-010 evidence, known provider limits, and remaining operational follow-ups to `docs/runbooks/identity-access.md`

## Dependencies & Execution Order

### Dependency Graph

```text
Phase 1 Setup
    -> Phase 2 Foundation (provider seams, decision, DB/job/audit/BFF primitives)
        -> Phase 3 US1 (invite, magic link, session)
            -> Phase 4 US2 (current authorization and ownership)
                -> Phase 5 US3 release/provider operation
                    -> Phase 6 US4 audit/webhooks/retention
                        -> Phase 7 Polish and release evidence
```

The provider decision and technical seams are intentionally completed in Phase
2 because UM-H1-013 depends on UM-H1-023. The remaining US3 tasks validate and
operate that decision after the US1 Adapters exist.

### Phase Dependencies

- **Setup (Phase 1)**: no feature dependency; T001–T006 establish files and tools.
- **Foundational (Phase 2)**: depends on Setup; T007–T016 block all stories.
- **US1 (Phase 3)**: depends on Foundation; T017–T022 are test-first and can run in parallel, then T023–T032 implement in dependency order.
- **US2 (Phase 4)**: depends on US1 session/principal interfaces; T034–T036 can run in parallel, then T037–T040 implement the matrix.
- **US3 (Phase 5)**: depends on Foundation and the provider Adapters from US1; T042–T044 can run in parallel, then T045–T048 operate and release them.
- **US4 (Phase 6)**: depends on US1 event producers and US2 authorization decisions; T050–T052 can run in parallel, then T053–T056 implement evidence.
- **Polish (Phase 7)**: depends on all desired stories; release claims require T058–T062.

### User Story Dependencies

- **US1 (P1)**: no dependency on another user story after Foundation; this is the MVP.
- **US2 (P2)**: depends on US1's product session/principal seam, but its pure policy tests remain independently executable with fixtures.
- **US3 (P3)**: the decision record is a Foundation prerequisite; provider failure/exit and release operation depend on US1 Adapters and may run before US4.
- **US4 (P4)**: depends on event producers from US1/US2 and closes the audit/redaction evidence for all stories.

### Parallel Execution Examples

**US1 after Foundation**

- T017, T018, T019, T020, T021, and T022 can run in parallel because they touch separate test files and all use the completed Foundation fixtures.
- T023 and T024 can proceed in parallel after the tests; T025 follows the migration; T027 can proceed in parallel with T024 once T011/T012/T013 exist.

**US2 after US1 principal seam**

- T034, T035, and T036 can run in parallel.
- T037 can proceed while T039 prepares administration fixtures; T038 follows T037 and T025; T040 follows T038.

**US3 after provider Adapters**

- T042, T043, and T044 can run in parallel.
- T045 follows those tests; T046 and T047 can then proceed in parallel; T048 requires the smoke evidence.

**US4 after access flows**

- T050, T051, and T052 can run in parallel.
- T053 follows the event tests; T054 follows provider webhook tests; T055 and T056 follow the repository/event implementation.

## Implementation Strategy

### MVP First — User Story 1 Only

1. Complete Setup and Foundational phases, including the provider decision and
   local fakes.
2. Complete US1 test-first through T033.
3. Stop and validate the invited first/repeat access journey, all link states,
   exact rate limits, seven-day idle boundary, logout, and redaction checks.
4. Deploy/demo only after the isolated preview provider smoke in T047 passes.

### Incremental Delivery

1. Add US2's deny-by-default authorization matrix and protected layout.
2. Add US3's environment/provider outage, exit, and access-gate release checks.
3. Add US4's webhook, audit reconstruction, retention, and redaction evidence.
4. Run Phase 7 before claiming SC-001–SC-010 or production readiness.

## Notes

- Every task has a checkbox, sequential ID, exact path, and required story
  label when it belongs to a user-story phase.
- `[P]` appears only where files and prerequisites are independent.
- No task adds invitation management UI, open registration, passwords, MFA,
  social login, account merge, support content access, or product notifications.
- Provider calls never run inside a database transaction, and bearer material is
  never placed in durable job payloads, logs, traces, audit, or browser JSON.
