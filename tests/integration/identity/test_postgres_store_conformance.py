"""Real PostgreSQL conformance tests for the identity persistence store."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.support.containers import ServiceConnection
from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.contracts import IdentityError
from umbral.domain.identity.models import (
    AccessAuditEvent,
    Invitation,
    MagicLinkAttempt,
    MagicLinkRequest,
    ProductSession,
    ProductUser,
)
from umbral.infrastructure.db.repositories.identity import SqlAlchemyIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.ops.identity import build_access_report, export_identity_snapshot

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def store_factory(postgres_container: ServiceConnection):
    """Use the migrated schema, rather than metadata creation, as production does."""

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_container.url)
    command.upgrade(config, "head")
    engine = create_engine(postgres_container.url)
    factory = sessionmaker(engine)
    try:
        yield lambda: SqlAlchemyIdentityStore(
            factory, fingerprint_key=b"postgres-test-key", environment="test"
        )
    finally:
        engine.dispose()


def _request() -> MagicLinkRequest:
    return MagicLinkRequest(
        uuid4(),
        b"e" * 32,
        b"o" * 32,
        "eligible",
        NOW,
        NOW + timedelta(hours=24),
        uuid4(),
    )


def test_store_reloads_domain_state_and_safe_export_after_restart(
    store_factory,
) -> None:
    """Catches process-local state or an export that leaks credentials/addresses."""

    store = store_factory()
    invitation = Invitation.new("person@example.com")
    request = _request()
    user = ProductUser(
        uuid4(), "person@example.com", created_at=NOW, status_changed_at=NOW
    )
    attempt = MagicLinkAttempt(
        uuid4(),
        request.id,
        "product_user",
        None,
        user.id,
        state="issued",
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=15),
    )
    session = ProductSession(uuid4(), user.id, attempt.id, b"d" * 32, NOW)
    with store.transaction():
        store.save_invitation(invitation)
        store.save_user(user)
        store.save_request(request)
        store.save_attempt(attempt)
        store.save_session(session)

    restarted = store_factory()
    assert restarted.user(user.id) == user
    assert restarted.attempt(attempt.id) == attempt
    assert restarted.session_by_digest(b"d" * 32) == session
    export = export_identity_snapshot(restarted)
    assert export == [
        {"user_id": str(user.id), "status": "active", "roles": [], "links": []}
    ]
    assert "person@example.com" not in repr(export)
    assert "d" * 32 not in repr(export)


def test_provider_dedupe_is_atomic_across_store_instances(store_factory) -> None:
    """Catches a process-local webhook claim or a duplicate audit event."""

    event = AccessAuditEvent(
        uuid4(),
        "magic_link.delivery_observed.v1",
        "observed",
        "email_delivered",
        uuid4(),
        NOW,
        provider="email",
        provider_event_id="evt-cross-instance",
    )

    def append_once() -> bool:
        store = store_factory()
        with store.transaction():
            return store.append_provider_audit_once(
                "email", "evt-cross-instance", event
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: append_once(), range(2)))

    reader = store_factory()
    assert sorted(outcomes) == [False, True]
    assert reader.audit_events() == (event,)


def test_transaction_rollback_leaves_no_identity_or_audit_row(store_factory) -> None:
    """Catches a store that commits one part of an access decision independently."""

    store = store_factory()
    invitation = Invitation.new("rollback@example.com")
    event = AccessAuditEvent(
        uuid4(),
        "invitation.preloaded.v1",
        "accepted",
        "eligible",
        uuid4(),
        NOW,
        invitation_id=invitation.id,
    )
    with pytest.raises(RuntimeError, match="rollback"):
        with store.transaction():
            store.save_invitation(invitation)
            store.append_audit(event)
            raise RuntimeError("rollback")

    restarted = store_factory()
    assert restarted.invitation(invitation.id) is None
    assert restarted.audit_events() == ()


def test_rate_limit_serializes_concurrent_requests_and_report_restarts(
    store_factory,
) -> None:
    """Catches limiter races that let both concurrent fourth requests through."""

    def request_once() -> int:
        store = store_factory()
        with store.transaction():
            count = store.recent_requests(b"e" * 32, now=NOW, field="email_fingerprint")
            store.save_request(_request())
            return count

    with ThreadPoolExecutor(max_workers=4) as executor:
        counts = list(executor.map(lambda _: request_once(), range(4)))

    report = build_access_report(store_factory())
    assert sorted(counts) == [0, 1, 2, 3]
    assert report["sessions"] == 0


def test_concurrent_confirmation_consumes_one_attempt_once(store_factory) -> None:
    """Catches confirmation races that create two sessions for one link."""

    store = store_factory()
    provider = FakeIdentityProvider()
    email = RecordingEmailAdapter()
    access = IdentityAccess(store, provider, email)
    invitation = Invitation.new("person@example.com")
    request = _request()
    attempt = MagicLinkAttempt(uuid4(), request.id, "invitation", invitation.id, None)
    with store.transaction():
        store.save_invitation(invitation)
        store.save_request(request)
        store.save_attempt(attempt)
    access.issue_attempt(attempt.id, now=NOW)
    token_hash = str(email.messages[0]["capture_url"]).split("token_hash=", 1)[1]

    def confirm() -> str:
        try:
            return str(
                access.confirm_magic_link(
                    attempt_id=attempt.id, token_hash=token_hash, now=NOW
                ).session_id
            )
        except IdentityError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: confirm(), range(2)))

    successful = [outcome for outcome in outcomes if outcome != "auth.link_unavailable"]
    assert len(successful) == 1
    assert outcomes.count("auth.link_unavailable") == 1
    assert store_factory().session_count() == 1
