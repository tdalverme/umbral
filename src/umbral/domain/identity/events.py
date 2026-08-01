"""Closed event and reason registry; event payloads are metadata-only."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Mapping

EVENT_RESULTS: dict[str, frozenset[str]] = {
    "invitation.preloaded.v1": frozenset({"accepted", "denied"}),
    "magic_link.requested.v1": frozenset({"accepted", "denied"}),
    "magic_link.issue_started.v1": frozenset({"accepted"}),
    "magic_link.issued.v1": frozenset({"accepted"}),
    "magic_link.issue_failed.v1": frozenset({"failed"}),
    "magic_link.delivery_observed.v1": frozenset({"observed"}),
    "provider.event_ignored.v1": frozenset({"observed"}),
    "magic_link.expired.v1": frozenset({"denied"}),
    "magic_link.superseded.v1": frozenset({"denied"}),
    "magic_link.consumed.v1": frozenset({"accepted"}),
    "magic_link.reused.v1": frozenset({"denied"}),
    "identity.linked.v1": frozenset({"accepted"}),
    "identity.conflict.v1": frozenset({"denied"}),
    "user.activated.v1": frozenset({"accepted"}),
    "user.status_changed.v1": frozenset({"accepted", "denied"}),
    "role.granted.v1": frozenset({"accepted", "denied"}),
    "role.revoked.v1": frozenset({"accepted", "denied"}),
    "session.started.v1": frozenset({"accepted"}),
    "session.ended.v1": frozenset({"accepted", "observed"}),
    "authorization.allowed.v1": frozenset({"allowed"}),
    "authorization.denied.v1": frozenset({"denied"}),
}

REASONS = frozenset(
    {
        "eligible", "not_eligible", "email_rate_limited", "origin_rate_limited",
        "both_rate_limited", "provider_accepted", "provider_rejected",
        "provider_unavailable", "provider_result_unknown", "email_accepted",
        "email_delivered", "email_delayed", "email_bounced", "email_complained",
        "email_rejected", "email_unavailable", "link_invalid", "link_expired",
        "link_consumed", "link_superseded", "issuer_mismatch", "email_mismatch",
        "subject_conflict", "product_email_conflict", "missing_verified_attribute",
        "user_inactive", "session_missing", "session_revoked", "session_idle_expired",
        "action_unknown", "role_unknown", "role_not_allowed", "owner_missing",
        "owner_ambiguous", "owner_mismatch", "logout", "administrator_change",
        "zero_admin_bootstrap", "eligible", "provider_signature_invalid",
        "ignored",
    }
)

FORBIDDEN_KEYS = frozenset(
    {
        "email", "normalized_email", "token", "token_hash", "cookie", "session_token",
        "raw_body", "body", "password", "secret", "authorization", "url", "query",
        "recipient", "subject", "message",
    }
)


def validate_event(*, event_type: str, result: str, reason: str, fields: Mapping[str, object]) -> None:
    if event_type not in EVENT_RESULTS or result not in EVENT_RESULTS[event_type]:
        raise ValueError("event type/result is not registered")
    if reason not in REASONS:
        raise ValueError("event reason is not registered")
    if any(key.lower() in FORBIDDEN_KEYS for key in fields):
        raise ValueError("sensitive event field is forbidden")
    for value in fields.values():
        if isinstance(value, Mapping):
            validate_no_sensitive_fields(value)


def validate_no_sensitive_fields(fields: Mapping[str, object]) -> None:
    if any(key.lower() in FORBIDDEN_KEYS for key in fields):
        raise ValueError("sensitive telemetry field is forbidden")
    for value in fields.values():
        if isinstance(value, Mapping):
            validate_no_sensitive_fields(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, Mapping):
                    validate_no_sensitive_fields(item)
