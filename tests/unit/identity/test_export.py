from __future__ import annotations

from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

from tests.support.identity import access_with_recording_jobs, requested_attempt
from umbral.application.identity.administration import AccessAdministration
from umbral.application.identity.ports import IdentityStore
from umbral.domain.identity.models import (
    IdentityExportLink,
    IdentityExportRecord,
    IdentityReport,
)
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.ops.identity import build_access_report, export_identity_snapshot


class _ProjectedIdentityStore:
    def identity_report(self) -> IdentityReport:
        return IdentityReport(
            event_counts=(("authorization.allowed.v1", 2),),
            reason_counts=(("eligible", 2),),
            user_count=1,
            session_count=1,
        )

    def exportable_identity_views(self) -> tuple[IdentityExportRecord, ...]:
        return (
            IdentityExportRecord(
                user_id=uuid4(),
                status="active",
                roles=("user",),
                links=(IdentityExportLink("provider", "issuer", "subject"),),
            ),
        )

    def audit_events(self):  # type: ignore[no-untyped-def]
        raise AssertionError("operator report must use the aggregate projection")

    def exportable_identities(self):  # type: ignore[no-untyped-def]
        raise AssertionError("operator export must use the batch projection")


def test_identity_export_contains_only_stable_internal_references() -> None:
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    email = RecordingEmailAdapter()
    access = access_with_recording_jobs(store, FakeIdentityProvider(), email)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=now,
    )
    attempt = requested_attempt(access, store)
    access.issue_attempt(attempt.id, now=now)
    token_hash = str(email.messages[0]["capture_url"]).split("token_hash=", 1)[1]
    access.confirm_magic_link(
        attempt_id=attempt.id,
        token_hash=str(token_hash),
        now=now,
    )
    exported = export_identity_snapshot(store)
    assert exported and exported[0]["roles"] == ["user"]
    assert "normalized_email" not in str(exported)
    assert "token" not in str(exported).lower()


def test_operator_reporting_uses_read_only_projections() -> None:
    """Catches report paths that load all audits or issue one role query per user."""

    store = _ProjectedIdentityStore()
    projected = cast(IdentityStore, store)

    assert build_access_report(projected) == {
        "events": {"authorization.allowed.v1": 2},
        "reasons": {"eligible": 2},
        "users": 1,
        "sessions": 1,
    }
    exported = export_identity_snapshot(projected)
    assert exported[0]["roles"] == ["user"]
    assert exported[0]["links"] == [
        {"provider": "provider", "issuer": "issuer", "subject": "subject"}
    ]
