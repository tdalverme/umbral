# Research: Private Beta Identity

**Feature**: `002-private-beta-identity`

**Date**: 2026-07-29

**Status**: Decisions resolved; no planning clarification remains

## Decision Summary

| Concern | Decision |
| --- | --- |
| Identity proof | Supabase Auth behind an Umbral-owned port |
| Transactional auth email | Resend behind an Umbral-owned port |
| Product identity truth | Umbral PostgreSQL |
| Browser/product session | Opaque Umbral token, SHA-256 hash stored in PostgreSQL |
| Product authorization | Deterministic Umbral policy using current user, roles, action, and ownership |
| Public web boundary | Next.js BFF; FastAPI stays private |
| Link scanner defense | `GET` captures into a transient cookie; explicit user `POST` consumes |
| Request abuse control | Exact PostgreSQL rolling window, 3/email and 20/origin per 15 minutes |
| Provider work | Durable foundation issue job; no raw email in the queue |
| Provider failure after side effect starts | Fail attempt safely; no automatic replay of bearer material |
| Local support | Deterministic identity/email fakes plus Mailpit; optional Supabase local conformance |

## Research Method

The comparison uses current first-party provider documentation and pricing
available on 2026-07-29. Supabase's Auth changelog was checked for relevant
breaking changes. The June 2026 free-tier email-template restriction affects
Supabase's default SMTP, not the selected `generate_link` plus separate Resend
flow; it reinforces the decision not to depend on shared Supabase email.

Relevant primary references:

- [Supabase Auth passwordless email](https://supabase.com/docs/guides/auth/auth-email-passwordless)
- [Supabase Python admin `generate_link`](https://supabase.com/docs/reference/python/auth-admin-generatelink)
- [Supabase Auth email templates and scanner guidance](https://supabase.com/docs/guides/auth/auth-email-templates)
- [Supabase Auth sessions](https://supabase.com/docs/guides/auth/sessions)
- [Supabase Auth rate limits](https://supabase.com/docs/guides/auth/rate-limits)
- [Supabase local Auth configuration](https://supabase.com/docs/guides/local-development/cli/config)
- [Supabase user data management](https://supabase.com/docs/guides/auth/managing-user-data)
- [Supabase self-hosting](https://supabase.com/docs/guides/self-hosting)
- [Supabase self-hosted/platform restore](https://supabase.com/docs/guides/self-hosting/restore-from-platform)
- [Supabase Auth changelog](https://supabase.com/changelog?tags=auth)
- [June 2026 email-template breaking change](https://supabase.com/changelog/46599-changes-to-email-template-customisation-on-free-tier)
- [Supabase pricing](https://supabase.com/pricing)
- [Auth0 passwordless code/link endpoint](https://auth0.com/docs/api/authentication/passwordless/get-code-or-link)
- [Auth0 user migration/export](https://auth0.com/docs/manage-users/user-migration)
- [Auth0 pricing](https://auth0.com/pricing)
- [Resend Python SDK](https://resend.com/python)
- [Resend idempotency keys](https://resend.com/docs/dashboard/emails/idempotency-keys)
- [Resend webhooks](https://resend.com/docs/webhooks/introduction)
- [Resend SMTP behavior](https://resend.com/docs/send-with-smtp)
- [Resend pricing](https://resend.com/pricing)
- [Postmark email API](https://postmarkapp.com/developer/user-guide/send-email-with-api)
- [Postmark SMTP](https://postmarkapp.com/developer/user-guide/send-email-with-smtp)
- [Postmark webhooks](https://postmarkapp.com/developer/webhooks/webhooks-overview)
- [Postmark pricing](https://postmarkapp.com/pricing/)

## Identity Provider Comparison

| Criterion | Supabase Auth | Auth0 |
| --- | --- | --- |
| Magic link | Native passwordless email; one-time tokens; configured expiry; server-side `token_hash` verification | Native passwordless email through Authentication API |
| Independent FastAPI validation | Admin can generate link/token hash; server verifies with Auth and extracts stable provider subject plus verified email | Server can complete passwordless flow and validate Auth0-issued identity |
| Latest-link invalidation | Provider one-time behavior exists, but a portable guarantee that every prior generated link is revoked is not relied on; Umbral's current-attempt check is authoritative | Provider behavior exists but still requires an Umbral current-attempt gate for replaceability |
| Open registration control | Umbral calls admin generation only after local eligibility; no public Supabase client/key is shipped; signup is disabled where compatible | Passwordless connection/rules can restrict access; local Umbral invitation check is still required |
| Product-data isolation | Product DB is separate; provider sees only identity data needed for proof | Product DB is separate; provider sees only identity data needed for proof |
| Local development | Supabase CLI/local Auth and open-source self-hosting are available; deterministic fake remains the default test path | No equivalent self-hosted Auth0 runtime; tests rely on mocks/tenant |
| Exit strategy | Users can be exported; Auth is open source/self-hostable; Umbral stores product users/roles/sessions independently | User export/migration is supported, but runtime is proprietary and not self-hostable |
| Observability | Auth logs/dashboard plus adapter metrics; Python client feature status is beta and must be pinned/conformance-tested | Mature tenant logs and attack protection; operational behavior remains tenant-specific |
| Cost at planning date | Free allowance is sufficient for beta; Pro begins around USD 25/month and includes a higher MAU allowance | Free tier covers a larger early MAU allowance; Essentials starts around USD 35/month, subject to tenant/features |
| Main risk | Python client and hosted behavior can change; provider creates an external Auth user when admin magic link is generated | Higher proprietary lock-in and weaker local parity |

### Decision

Use **Supabase Auth** as the production identity-proof Adapter.

### Rationale

Supabase provides the required one-time passwordless proof, a documented
server-side token-hash flow, controlled admin link generation, separate
projects, local/self-hosted options, and user export. These capabilities create
a credible exit path while allowing FastAPI to remain the verifier. The lower
starting cost fits a controlled beta.

Umbral does not trust Supabase for:

- invitation eligibility;
- current user status;
- latest locally valid attempt;
- roles or ownership;
- product session lifetime/revocation;
- product audit.

The adapter returns only `provider`, stable `subject`, verified normalized
email, proof time, and a provider-session revocation handle. Supabase access and
refresh tokens never become the browser's product session.

### Alternatives Rejected

- **Auth0**: technically viable and operationally mature, but adds stronger
  proprietary coupling and weaker local/self-host parity without solving the
  need for local invitation, authorization, session, and audit truth.
- **Custom magic-link cryptography**: gives maximum control but expands the
  security-sensitive implementation surface for token generation, hashing,
  expiry, replay, email verification, and incident response. It is not
  justified for H1.
- **Supabase browser session as product session**: cannot directly express the
  exact Umbral seven-day idle rule with immediate role/status freshness and
  would couple every protected operation to provider JWT/session semantics.

## Identity Provider Risks and Mitigations

| Risk | Owner | Mitigation / exit |
| --- | --- | --- |
| Provider generates an external user before Umbral activation completes | Platform | Treat it as non-authoritative proof data; it grants no Product API access; reconcile orphan provider users by internal attempt reference and retention policy |
| Admin generation or Python response shape changes | Platform | Pin the SDK and lockfile; run provider conformance in preview before promotion; map all provider types/errors inside one Adapter |
| Previous provider token remains technically verifiable | Trust | Check local attempt is current before provider verification and again in activation transaction; only current `issued` attempt can create an Umbral session |
| Provider generation invalidates an older token before email delivery succeeds | Trust | Accept fail-closed behavior; record a stable failure; retain neutral response and let the user request a new link |
| Provider returns a session/access token | Platform | Extract proof server-side, never forward it, revoke best-effort, and use only the opaque Umbral session |
| Hosted outage | Platform | Existing product sessions continue; new issue/confirmation fails closed; readiness is degraded rather than down |
| Credential or environment crossover | Platform | Separate project/secret/redirect allowlist per environment; reject provider issuer/project mismatch; no secret in browser or `NEXT_PUBLIC_*` |
| Provider exit | Platform | Export provider subjects/emails; keep Umbral user/link/role/ownership IDs stable; implement a replacement Adapter and require re-proof on next login |

## Email Provider Comparison

| Criterion | Resend | Postmark |
| --- | --- | --- |
| Transactional API | Simple HTTP and official Python SDK | Mature HTTP API |
| Idempotency | API idempotency keys retained for 24 hours | Message IDs and submission APIs, but no equivalent documented request-key workflow used by this plan |
| Delivery events | Signed, at-least-once webhooks with replay/deduplication guidance | Mature delivery/bounce webhooks |
| SMTP | Supported, but synchronous SMTP acceptance does not prove final delivery | Supported and mature |
| Local workflow | Recording Adapter/Mailpit; provider test mode and webhook tooling | Test server tokens/webhook tooling |
| Cost at planning date | Free approximately 3,000 emails/month with daily cap; Pro approximately USD 20/month for 50,000 | Free developer allowance around 100 emails/month; Basic approximately USD 15/month for 10,000 |
| Main risk | Younger service and lower free daily cap | Higher beta cost per message and less convenient request idempotency for this flow |

### Decision

Use **Resend's HTTP API** as the production transactional-email Adapter.

### Rationale

The API offers a small integration surface, an official Python SDK, a
documented idempotency key, and signed at-least-once webhook delivery. The free
allowance is adequate for the cohort and the paid step is modest. Keeping it
separate from Supabase SMTP makes provider responsibilities explicit and
replaceable.

Click and open tracking are disabled for authentication messages. These
features add no product value here and cause avoidable link handling and
personal-data exposure.

### Alternative Rejected

**Postmark** remains the preferred fallback if delivery quality/support becomes
the dominant concern. It is technically suitable, but its initial allowance
and price are less favorable for the beta, and Resend's request idempotency and
webhook developer workflow better match the selected issue job.

## Email Provider Risks and Mitigations

| Risk | Owner | Mitigation / exit |
| --- | --- | --- |
| API accepts a message but response is lost | Platform | Attempt fails closed; any delivered link remains locally unusable; user requests a new link; do not persist/replay bearer material |
| Duplicate issue-job delivery | Platform | Claim attempt once in PostgreSQL; use deterministic Resend idempotency key; terminal/issuing attempts do not call providers again |
| Duplicate/out-of-order webhooks | Platform | Verify raw-body signature; unique provider event ID; monotonic local delivery projection; audit every accepted transition |
| Webhook payload contains recipient PII | Trust | Parse only after verification, map to internal attempt by provider message ID, discard raw payload and recipient fields, never log body |
| Delivery degradation/bounce | Operations | Bounded metrics and audit reason; run provider/domain smoke; switch the email Adapter to Postmark without changing identity/application interfaces |

## Product Session Decision

### Decision

Issue a random opaque token with at least 256 bits of entropy. Send it only in
an `HttpOnly` cookie and store only its SHA-256 digest. PostgreSQL records
`last_activity_at`, `revoked_at`, and stable revocation reason. There is no
absolute expiry while valid protected activity occurs at intervals shorter than
seven days.

### Rationale

This directly implements the clarified requirement:

- valid protected operation before seven full idle days keeps the session alive
  and resets the idle window;
- public, denied, failed, and background operations do not;
- at the exact boundary, PostgreSQL time and a conditional row lock decide once;
- disabling a user or removing a role affects the next operation;
- logout is immediate.

### Alternatives Rejected

- **Provider refresh/access tokens in the browser**: role/status claims can be
  stale and the provider's session controls do not become Umbral's exact
  product-session contract.
- **Stateless Umbral JWT**: immediate logout/status/role revocation still needs
  a database lookup or revocation list, removing the expected advantage.
- **Redis-only session**: loses authoritative access state and audit on cache
  loss, contradicting foundation persistence rules.

## Neutral Request and Issue-Job Decision

### Decision

The request transaction performs normalization, exact rate-limit reservation,
eligibility, minimized audit, eligible attempt creation, and foundation
job/outbox submission. It returns the same `202` body before any identity/email
provider call. The job carries only `attempt_id`.

### Rationale

Provider calls only for eligible emails create an observable latency
difference if performed in the public request. The durable job keeps public
behavior neutral, avoids raw email in Redis/outbox payloads, and reuses the
foundation's at-least-once dispatch. The worker reloads email from the eligible
invitation/user.

Once the attempt enters `issuing`, external side effects are not automatically
replayed. The worker writes a terminal safe failure after a timeout or
interruption and asks the person to make another public request. This is a
deliberate exception to ordinary retryable jobs because the bearer link is
never persisted and regenerating it would change the Resend idempotent payload.

### Alternatives Rejected

- **Synchronous provider calls**: leaks eligibility through latency, increases
  public timeout exposure, and couples browser acknowledgement to providers.
- **Queue raw email/token**: expands personal/bearer data into Redis and job
  telemetry.
- **Persist encrypted token for automatic retry**: improves recovery but adds
  encryption-key lifecycle, token cleanup, and a durable bearer store that H1
  does not need.

## Link Capture and Scanner Defense

### Decision

The email link lands on `GET /auth/capture`, which performs no provider
verification. It validates bounded query fields, puts them in a short-lived
`HttpOnly; Secure; SameSite=Strict` transient cookie, and redirects to a URL
without query parameters. A human presses the confirmation button, producing
the only consuming `POST`.

### Rationale

Email security products and clients can prefetch links. Supabase documents that
automatic confirmation URLs can be consumed before the intended person reaches
them. A non-consuming GET plus explicit POST prevents that class of false
expiry and keeps token hashes out of page source, browser JavaScript, referrers,
and later URLs.

### Alternatives Rejected

- **Consume on GET**: unsafe under email prefetch.
- **Put token hash in client state/localStorage**: exposes bearer material to
  JavaScript and persistence.
- **Supabase-hosted redirect/implicit browser session**: bypasses Umbral's
  invitation/latest-attempt/session transaction.

## Rate-Limit Decision

### Decision

Use PostgreSQL request rows and transaction-scoped advisory locks to implement
an exact rolling 15-minute window. Lock order is email fingerprint then origin
fingerprint. Count both dimensions in the same transaction; reserve only if
both are below 3 and 20.

Email and origin keys are environment-scoped HMAC-SHA-256 fingerprints. The web
BFF derives origin from the trusted platform address after overwriting client
headers. The API derives email fingerprint after normalization. Fingerprint
rows expire after 24 hours.

### Rationale

The requirement is exact under concurrency and determines whether a new link
can invalidate an older one. Redis counters and approximate fixed buckets would
create boundary anomalies or a second source of truth. PostgreSQL advisory
locks serialize only the two small contention keys and keep the decision with
the durable attempt/audit transaction.

### Alternatives Rejected

- **Redis-only sliding window**: fast but disposable and hard to transact with
  attempt creation.
- **Fixed 15-minute buckets**: permits bursts across bucket boundaries and does
  not implement the clarified rolling window.
- **Raw email/IP rows**: unnecessary personal-data retention.

## Authorization Decision

### Decision

Use a pure finite policy over:

`(active principal, current roles, action, optional resource owner)`.

The policy has no wildcard allow. `operator` grants only registered operational
actions; `administrator` grants only registered access-administration actions;
neither grants private user-content access. The application guard validates
the session and current database state for every protected operation and
persists allow/deny evidence.

### Rationale

This provides a small, testable interface and forces later increments to name
new actions and ownership requirements. It prevents framework routes,
provider claims, and role labels from becoming accidental authorization rules.

### Alternatives Rejected

- **Role checks in route handlers**: duplicates rules, makes deny-by-default
  hard to prove, and invites drift.
- **Provider roles/app metadata**: claims can be stale and moves product truth
  outside Umbral.
- **Administrator superuser wildcard**: contradicts the explicit prohibition
  on implicit private-content access.

## PostgreSQL Modeling Decisions

- Follow foundation application-generated UUID identities and UTC
  `timestamptz`.
- Use bounded text plus named check constraints for states/roles so migrations
  can evolve without database enum replacement.
- Index every foreign key.
- Use partial indexes for current sessions, current roles, issued attempts, and
  unprocessed webhook events.
- Use equality columns before range timestamps in rolling-window composite
  indexes.
- Keep transactions short and never call Supabase or Resend while holding row
  or advisory locks.
- Acquire locks in one documented order to prevent deadlocks.
- Use the least-privileged application role; no provider/browser has product
  table grants. Product tables are not exposed through Supabase Data API.

## Resolved Unknowns

All Technical Context questions are resolved. Implementation still requires
ordinary environment provisioning choices—actual account IDs, secrets, domain
verification, and named human owners—but those are runbook inputs, not
architecture or specification clarifications.
