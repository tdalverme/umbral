# Contract: Identity Proof and Transactional Email Seams

## Purpose

Keep third-party identity and email behavior behind two narrow interfaces.
Application callers and tests use these interfaces; no Supabase/Resend type,
exception, token object, or configuration crosses the seam.

## Identity-Proof Interface

```python
class IdentityProofProvider(Protocol):
    def generate_magic_link(
        self,
        *,
        normalized_email: str,
        redirect_url: str,
        lifetime_seconds: int,
        correlation_id: UUID,
    ) -> GeneratedMagicLink: ...

    def verify_magic_link(
        self,
        *,
        token_hash: SecretStr,
        expected_issuer: str,
        correlation_id: UUID,
    ) -> VerifiedIdentity: ...

    def revoke_provider_session(
        self,
        *,
        revocation_handle: SecretStr,
        correlation_id: UUID,
    ) -> None: ...
```

`GeneratedMagicLink` contains:

- secret token hash/link material held only in worker memory;
- canonical provider name and issuer;
- provider generation time;
- expiry no later than generation plus 900 seconds.

`VerifiedIdentity` contains:

- provider name;
- canonical issuer/project;
- stable provider subject;
- verified normalized email;
- verification time;
- short-lived revocation handle, if the provider created a session.

All bearer fields use secret wrappers whose representation is redacted.

## Identity Invariants

- `redirect_url` must exactly match one configured Umbral capture origin/path.
- Adapter enforces `lifetime_seconds <= 900`; environment configuration must
  also set the provider email OTP/link expiry to 900 seconds.
- Provider issuer/project must equal the environment configuration.
- Email must be provider-verified and normalize to the expected access subject.
- Missing subject, unverified email, mismatched issuer, or malformed response is
  `IdentityProofRejected`.
- Timeout, transport failure, or provider 5xx is
  `IdentityProofUnavailable`.
- An invalid, expired, or consumed proof is `IdentityProofInvalid`.
- Provider exception text/body is never propagated.
- Provider access/refresh tokens never reach FastAPI response or browser.
- Revocation is best-effort after Umbral has extracted proof; revocation failure
  emits a bounded operational event but cannot create authorization.

## Supabase Adapter Mapping

- Use admin `generate_link(type="magiclink")` only after local eligibility.
- Use the returned hashed token to construct the Umbral capture URL; do not send
  the provider's implicit browser-session URL.
- Verify server-side using the provider's token-hash verification operation and
  the `magiclink` verification type required by conformance.
- No Supabase client or service key is bundled into browser code.
- Open signup is disabled/configured so only the server-side admin path used by
  Umbral can provision proof users.
- The Adapter accepts pinned SDK/configuration dependencies; it never creates
  them internally.

## Transactional-Email Interface

```python
class TransactionalEmailSender(Protocol):
    def send_magic_link(
        self,
        *,
        attempt_id: UUID,
        normalized_email: str,
        capture_url: SecretStr,
        expires_at: datetime,
        idempotency_key: str,
        correlation_id: UUID,
    ) -> EmailAcceptance: ...

    def verify_webhook(
        self,
        *,
        raw_body: SecretBytes,
        headers: Mapping[str, str],
        received_at: datetime,
    ) -> VerifiedEmailEvent: ...
```

`EmailAcceptance` contains only provider, bounded message ID, and accepted time.
`VerifiedEmailEvent` contains only provider event ID, message ID, allowlisted
event kind, observed time, and stable failure classification.

## Email Invariants

- Idempotency key is exactly `identity.magic-link/{attempt_id}`.
- Sender/domain and destination environment are configured, not caller input.
- Click/open tracking is disabled.
- Email body is rendered inside the Adapter from an approved versioned template.
- Raw body, capture URL, token hash, recipient, and provider response body are
  never logged or persisted.
- Signature and timestamp are verified against the unmodified body before
  parsing.
- Supported webhook events are accepted/delivered/delayed/bounced/complained;
  unknown kinds are ignored with bounded diagnostics.
- Provider event IDs are at-least-once and must be deduplicated in PostgreSQL.

## Error Taxonomy

| Error | Retry by same issue attempt | Public behavior |
| --- | --- | --- |
| `IdentityProofRejected` | no | neutral request acknowledgement or safe confirmation denial |
| `IdentityProofInvalid` | no | recoverable link-unavailable problem |
| `IdentityProofUnavailable` | no automatic bearer replay | neutral request; confirmation retry-later without session |
| `EmailRejected` | no | neutral request; failed attempt |
| `EmailUnavailable` | no automatic bearer replay | neutral request; failed attempt |
| `WebhookInvalid` | no | 401/400 to provider, bounded diagnostic |

The foundation job transport can redeliver a job, but the PostgreSQL attempt
claim ensures a provider call occurs at most once after `issuing` begins.

## Required Conformance Suite

Run identical observable tests against fake and production-candidate Adapters:

1. generated proof expires within 900 seconds;
2. only configured redirect is accepted;
3. valid proof yields stable subject plus verified email;
4. invalid/expired/consumed proof is normalized safely;
5. wrong environment issuer is rejected;
6. generated bearer and provider tokens never appear in representation/logs;
7. same email can log in again with a later proof;
8. ten verification replays create no provider-side product authority;
9. email idempotency key is stable for one attempt;
10. signed webhook accepts, tampered/stale webhook rejects, duplicate maps to
    the same provider event ID;
11. outage/timeout maps to a bounded error with no raw response;
12. no SDK/provider type crosses the application interface.

Preview conformance is required before production promotion. Local fake success
alone does not close the provider decision.
