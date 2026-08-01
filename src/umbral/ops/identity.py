"""Operator-safe reconstruction of access decisions."""

from __future__ import annotations

from umbral.application.identity.ports import IdentityStore


def build_access_report(store: IdentityStore) -> dict[str, object]:
    """Return bounded event counts and reasons, never PII or bearer material."""

    report = store.identity_report()
    return {
        "events": dict(report.event_counts),
        "reasons": dict(report.reason_counts),
        "users": report.user_count,
        "sessions": report.session_count,
    }


def export_identity_snapshot(store: IdentityStore) -> list[dict[str, object]]:
    """Export stable product identity references without email or bearer data."""

    rows: list[dict[str, object]] = []
    for identity in store.exportable_identity_views():
        links = [
            {
                "provider": link.provider,
                "issuer": link.issuer,
                "subject": link.subject,
            }
            for link in identity.links
        ]
        rows.append(
            {
                "user_id": str(identity.user_id),
                "status": identity.status,
                "roles": list(identity.roles),
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
