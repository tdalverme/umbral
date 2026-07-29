"""Operator-safe reconstruction of access decisions."""

from __future__ import annotations

from collections import Counter

from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore


def build_access_report(store: InMemoryIdentityStore) -> dict[str, object]:
    """Return bounded event counts and reasons, never PII or bearer material."""

    events = Counter(event.event_type for event in store.audits)
    reasons = Counter(event.reason for event in store.audits)
    return {
        "events": dict(sorted(events.items())),
        "reasons": dict(sorted(reasons.items())),
        "users": len(store.users),
        "sessions": len(store.sessions),
    }


def export_identity_snapshot(store: InMemoryIdentityStore) -> list[dict[str, object]]:
    """Export stable product identity references without email or bearer data."""

    rows: list[dict[str, object]] = []
    for user in sorted(store.users.values(), key=lambda item: str(item.id)):
        links = [
            {
                "provider": link.provider,
                "issuer": link.provider_issuer,
                "subject": link.provider_subject,
            }
            for link in store.links.values()
            if link.product_user_id == user.id
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
