"""Operator-safe reconstruction of access decisions."""

from __future__ import annotations

from collections import Counter

from umbral.application.identity.ports import IdentityStore


def build_access_report(store: IdentityStore) -> dict[str, object]:
    """Return bounded event counts and reasons, never PII or bearer material."""

    audit_events = store.audit_events()
    events = Counter(event.event_type for event in audit_events)
    reasons = Counter(event.reason for event in audit_events)
    return {
        "events": dict(sorted(events.items())),
        "reasons": dict(sorted(reasons.items())),
        "users": len(store.exportable_identities()),
        "sessions": store.session_count(),
    }


def export_identity_snapshot(store: IdentityStore) -> list[dict[str, object]]:
    """Export stable product identity references without email or bearer data."""

    rows: list[dict[str, object]] = []
    for user, identity_links in store.exportable_identities():
        links = [
            {
                "provider": link.provider,
                "issuer": link.provider_issuer,
                "subject": link.provider_subject,
            }
            for link in identity_links
        ]
        rows.append(
            {
                "user_id": str(user.id),
                "status": user.status,
                "roles": sorted(store.active_roles(user.id)),
                "links": sorted(
                    links,
                    key=lambda item: (
                        str(item["provider"]),
                        str(item["subject"]),
                    ),
                ),
            }
        )
    return rows
