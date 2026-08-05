"""Operator-safe reconstruction of access decisions."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Mapping

from umbral.application.identity.administration import AccessAdministration
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


def _preload_with_database(email: str, database_url: str) -> str:
    """Persist one controlled invitation using an operator-only database URL."""

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from umbral.infrastructure.db.repositories.identity import SqlAlchemyIdentityStore

    engine = create_engine(database_url)
    try:
        store = SqlAlchemyIdentityStore(sessionmaker(bind=engine))
        return str(AccessAdministration(store).preload_invitation(email).id)
    finally:
        engine.dispose()


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    preload_invitation: Callable[[str, str], str] | None = None,
) -> int:
    """Run a non-interactive identity operator command without echoing secrets."""

    parser = argparse.ArgumentParser(prog="python -m umbral.ops.identity")
    subparsers = parser.add_subparsers(dest="command", required=True)
    preload = subparsers.add_parser("preload-invitation")
    preload.add_argument("--email-env", required=True)
    preload.add_argument("--database-url-env", required=True)
    args = parser.parse_args(argv)
    values = os.environ if environ is None else environ
    email = values.get(args.email_env, "")
    database_url = values.get(args.database_url_env, "")
    if not email or not database_url:
        raise ValueError("operator environment input is unavailable")
    invitation_id = (preload_invitation or _preload_with_database)(email, database_url)
    print(
        json.dumps(
            {"invitation_id": str(invitation_id), "result": "accepted"},
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
