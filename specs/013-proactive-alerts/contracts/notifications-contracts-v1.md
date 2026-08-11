# Notifications Contracts v1 (H5)

**Feature**: 013-proactive-alerts | **Date**: 2026-08-11

Planning contract for the proactive alerts surface. Machine-checkable files:
`contracts/notifications/v1/notification-policy-v1.json`,
`contracts/notifications/v1/planner-golden-v1.json`, the events registry
(+6 `notification.*.v1`) and the additive OpenAPI
(`contracts/openapi/v1/openapi.json`).

## 1. HTTP surface (OpenAPI aditivo)

| Method | Path | Request | Response | Errors |
| --- | --- | --- | --- | --- |
| GET | `/api/v1/notifications/preferences` | — | preferences (current version) | 403 denied |
| PUT | `/api/v1/notifications/preferences` | `{email_enabled, inbox_enabled, timezone, quiet_hours_start, quiet_hours_end, digest_enabled, digest_local_hour, score_threshold, state}` | preferences (new version) | 403; 422 validation (timezone/quiet hours/range) |
| GET | `/api/v1/notifications/inbox?page_size=&after_position=&unread_only=` | — | inbox page (decision + reason + link) | 403 |
| PATCH | `/api/v1/notifications/inbox/{decision_id}` | `{read: bool}` | inbox item | 403; 404 `notifications.item_not_found` |
| POST | `/api/v1/notifications/unsubscribe` | `{token}` | 204 | 422 `notifications.token_invalid` / `notifications.token_expired` |
| GET | `/api/v1/notifications/unsubscribe` (web page) | `?token=` | HTML (confirm page) | — |

All operations require the product session cookie (except the unsubscribe
page/endpoint which validates the token without login) and
`product.notifications.*` actions; 0 cross access with manipulated ids.

## 2. Planner golden dataset (contract)

`planner-golden-v1.json`: cases with `item`, `history`, `preferences`,
`policy` and expected `decision` (trigger, reason_code, decision_state,
duplicate_of nullable). Families: `new_match_immediate`,
`new_match_digest`, `price_drop`, `duplicate`, `quiet_hours`,
`fatigue`, `digest_group`, `discarded`. Product-reviewed, 0 PII.

## 3. Notification policy (contract)

`notification-policy-v1.json`: versioned immutable policy — immediate score
threshold, fatigue cooldown hours, fatigue window, digest default hour,
max items per digest, quiet hours defaults. Pure constants consumed by the
planner; 0 PII.

## 4. Events (registry +6, 0 PII)

`notification.decision_created.v1` (decision_id, trigger, reason_code,
decision_state), `notification.delivered.v1` (decision_id, channel,
provider_message_id), `notification.delivery_failed.v1` (decision_id,
error_code), `notification.viewed.v1` (decision_id), `notification.acted.v1`
(decision_id, action), `notification.unsubscribed.v1` (search_profile_id).

## 5. Delivery contract

Decision + job `notifications.deliver` are persisted atomically via the
durable job runtime (H1-010). The worker is idempotent by provider message
id; lease/reclaim/backoff/dead-letter come from the existing runtime.
Templates receive ONLY fields of the persisted decision.

## 6. Unsubscribe token

`HMAC-SHA256(SECRET, user_id|search_profile_id|preferences_version|exp)` —
TTL 24h; a changed preferences version invalidates outstanding tokens;
token reuse or expiry is rejected with a typed error and audited.
