# Contract: Access Events and Email Webhooks

## Event Envelope

Every persisted access event contains only:

- versioned `event_type`;
- `event_version`;
- `result`;
- stable `reason`;
- internal references relevant to the event;
- actor kind/internal ID when known;
- registered action and policy version when authorizing;
- provider plus bounded provider event/message ID when relevant;
- environment;
- correlation ID;
- database timestamp.

No unregistered extension map is accepted in H1.

## Closed Event Registry

| Event type | Required references | Allowed results |
| --- | --- | --- |
| `invitation.preloaded.v1` | invitation, actor | accepted, denied |
| `magic_link.requested.v1` | request | accepted, denied |
| `magic_link.issue_started.v1` | request, attempt | accepted |
| `magic_link.issued.v1` | attempt | accepted |
| `magic_link.issue_failed.v1` | attempt | failed |
| `magic_link.delivery_observed.v1` | attempt, provider event | observed |
| `magic_link.expired.v1` | attempt | denied |
| `magic_link.superseded.v1` | old and new attempt correlation | denied |
| `magic_link.consumed.v1` | attempt | accepted |
| `magic_link.reused.v1` | attempt | denied |
| `identity.linked.v1` | user, attempt | accepted |
| `identity.conflict.v1` | attempt and safe internal candidates | denied |
| `user.activated.v1` | user, invitation | accepted |
| `user.status_changed.v1` | user, actor | accepted, denied |
| `role.granted.v1` | user, assignment, actor | accepted, denied |
| `role.revoked.v1` | user, assignment, actor | accepted, denied |
| `session.started.v1` | user, session, attempt | accepted |
| `session.ended.v1` | user, session | accepted, observed |
| `authorization.allowed.v1` | user, session, action, policy | allowed |
| `authorization.denied.v1` | action/policy and safe actor/session refs | denied |

## Stable Reason Registry

Initial reasons include:

- `eligible`, `not_eligible`;
- `email_rate_limited`, `origin_rate_limited`, `both_rate_limited`;
- `provider_accepted`, `provider_rejected`, `provider_unavailable`,
  `provider_result_unknown`;
- `email_accepted`, `email_delivered`, `email_delayed`, `email_bounced`,
  `email_complained`, `email_rejected`, `email_unavailable`;
- `link_invalid`, `link_expired`, `link_consumed`, `link_superseded`;
- `issuer_mismatch`, `email_mismatch`, `subject_conflict`,
  `product_email_conflict`, `missing_verified_attribute`;
- `user_inactive`, `session_missing`, `session_revoked`,
  `session_idle_expired`;
- `action_unknown`, `role_unknown`, `role_not_allowed`,
  `owner_missing`, `owner_ambiguous`, `owner_mismatch`;
- `logout`, `administrator_change`, `zero_admin_bootstrap`.

Provider error text/status bodies never become reasons. New reasons require a
contract/version update and redaction fixture.

## Forbidden Fields and Values

Recursive event/telemetry tests reject:

- raw or normalized email;
- raw client address or forwarding headers;
- cookie/session value or digest;
- token hash, OTP, action link, full URL, query string;
- Supabase access/refresh token or service key;
- Resend API/webhook secret;
- message subject/body/recipient list;
- request/response body, arbitrary headers, stack/exception text;
- product resource content or free-form operator note.

Opaque internal UUIDs and bounded provider message/event IDs are allowed.

## Resend Webhook Contract

The public web route forwards the exact bytes and these headers only:

- `svix-id`;
- `svix-timestamp`;
- `svix-signature`;
- internal correlation/BFF credential added by the web server.

FastAPI:

1. validates body size and timestamp tolerance;
2. verifies signature on raw bytes;
3. parses only after verification;
4. maps supported provider event to the closed local registry;
5. resolves attempt by stored provider message ID;
6. inserts with unique `(provider, provider_event_id)`;
7. applies only monotonic delivery projection;
8. discards raw payload and PII.

Ten duplicate deliveries persist one provider-event identity and never modify
authentication/link/session state.

Unknown valid event kinds return `204` and a bounded ignored metric; malformed
validly signed shapes return `400`; invalid signatures return `401`.

## Audit Atomicity

- Invitation, activation, link, role, status, session, and authorization-allow
  mutations commit with their required audit events.
- If required audit insert fails, the sensitive mutation fails closed.
- Provider generation/email happen outside transactions. Their local
  issued/failed state and audit commit together afterward.
- A sent email whose local success/audit cannot commit remains unusable because
  only a local current `issued` attempt can confirm.
- Authorization denials persist without touching session activity.

## Operational Signals

Allowed metric dimensions:

- event type/reason/result;
- environment;
- provider;
- route template;
- HTTP status class;
- policy version;
- bounded latency bucket.

Email/user/session/request/attempt/resource identifiers are not metric labels.
Logs/traces may use correlation and internal event ID as fields, subject to the
foundation closed allowlist and retention.

## Verification evidence (2026-07-31)

Executed from the `001-foundation-runtime` worktree:

```text
PYTHONPATH=src .venv/Scripts/python.exe -m pytest \
  tests/unit/identity/test_access_flow.py \
  tests/unit/identity/test_redaction.py \
  tests/unit/identity/test_retention.py \
  tests/contract/test_identity_redaction.py \
  tests/integration/identity/test_access_events.py \
  tests/integration/identity/test_email_webhooks.py \
  tests/integration/identity/test_provider_failures.py \
  tests/integration/identity/test_webhook_dedupe.py -q
15 passed
```

The evidence covers closed event emission, recursive redaction, retention,
raw-body webhook verification, stale/tampered rejection, provider-event
deduplication, and provider failure paths. This is the local evidence for
SC-005 and FR-024 through FR-026.
