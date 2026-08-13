"""Real PostgreSQL conformance tests for the identity persistence store."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.support.containers import ServiceConnection
from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.authorization import AccessControl
from umbral.application.identity.contracts import IdentityError
from umbral.domain.identity.models import (
    AccessAuditEvent,
    Invitation,
    MagicLinkAttempt,
    MagicLinkRequest,
    ProductSession,
    ProductUser,
    RoleAssignment,
)
from umbral.infrastructure.db.repositories.identity import SqlAlchemyIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.ops.identity import build_access_report, export_identity_snapshot

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def store_factory(
    postgres_container: ServiceConnection,
) -> Iterator[Callable[[], SqlAlchemyIdentityStore]]:
    """Use the migrated schema, rather than metadata creation, as production does."""

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_container.url)
    command.upgrade(config, "head")
    engine = create_engine(postgres_container.url)

    def new_store() -> SqlAlchemyIdentityStore:
        return SqlAlchemyIdentityStore(
            sessionmaker(engine),
            fingerprint_key=b"postgres-test-key",
            environment="test",
        )

    try:
        yield new_store
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
    store_factory: Callable[[], SqlAlchemyIdentityStore],
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


def test_provider_dedupe_is_atomic_across_store_instances(
    store_factory: Callable[[], SqlAlchemyIdentityStore],
) -> None:
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


def test_ignored_provider_event_is_validated_and_deduplicated(
    store_factory: Callable[[], SqlAlchemyIdentityStore],
) -> None:
    """Catches restart-unsafe ignored webhooks or an unregistered audit claim."""

    store = store_factory()
    with store.transaction():
        assert store.append_provider_audit_once("email", "evt-ignored", None)
    restarted = store_factory()
    with restarted.transaction():
        assert not restarted.append_provider_audit_once("email", "evt-ignored", None)

    events = store_factory().audit_events()
    assert len(events) == 1
    assert (events[0].event_type, events[0].result, events[0].reason) == (
        "provider.event_ignored.v1",
        "observed",
        "ignored",
    )


def test_transaction_rollback_leaves_no_identity_or_audit_row(
    store_factory: Callable[[], SqlAlchemyIdentityStore],
) -> None:
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


def test_nested_rollback_preserves_outer_transaction(
    store_factory: Callable[[], SqlAlchemyIdentityStore],
) -> None:
    """Catches nested failures that leak inner rows into an outer commit."""

    store = store_factory()
    outer = Invitation.new("outer@example.com")
    inner = Invitation.new("inner@example.com")
    event = AccessAuditEvent(
        uuid4(),
        "invitation.preloaded.v1",
        "accepted",
        "eligible",
        uuid4(),
        NOW,
        invitation_id=inner.id,
    )

    with store.transaction():
        store.save_invitation(outer)
        with pytest.raises(RuntimeError, match="inner"):
            with store.transaction():
                store.save_invitation(inner)
                store.append_audit(event)
                raise RuntimeError("inner")
        assert store.invitation(outer.id) == outer
        assert store.invitation(inner.id) is None
        assert store.audit_events() == ()

    restarted = store_factory()
    assert restarted.invitation(outer.id) == outer
    assert restarted.invitation(inner.id) is None
    assert restarted.audit_events() == ()


def test_rate_limit_serializes_concurrent_requests_and_report_restarts(
    store_factory: Callable[[], SqlAlchemyIdentityStore],
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


def test_concurrent_confirmation_consumes_one_attempt_once(
    store_factory: Callable[[], SqlAlchemyIdentityStore],
) -> None:
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


def test_concurrent_issuance_serializes_an_empty_subject(
    store_factory: Callable[[], SqlAlchemyIdentityStore],
) -> None:
    """Catches two issuers both seeing no current attempt for one invitation."""

    class BarrierEmail(RecordingEmailAdapter):
        def __init__(self) -> None:
            super().__init__()
            self._barrier = Barrier(2)

        def send_magic_link(self, **kwargs):  # type: ignore[no-untyped-def]
            acceptance = super().send_magic_link(**kwargs)
            self._barrier.wait(timeout=5)
            return acceptance

    store = store_factory()
    invitation = Invitation.new("issuance@example.com")
    first_request = _request()
    second_request = _request()
    first = MagicLinkAttempt(
        uuid4(), first_request.id, "invitation", invitation.id, None
    )
    second = MagicLinkAttempt(
        uuid4(), second_request.id, "invitation", invitation.id, None
    )
    with store.transaction():
        store.save_invitation(invitation)
        store.save_request(first_request)
        store.save_request(second_request)
        store.save_attempt(first)
        store.save_attempt(second)

    access = IdentityAccess(store, FakeIdentityProvider(), BarrierEmail())

    def issue(attempt_id):  # type: ignore[no-untyped-def]
        access.issue_attempt(attempt_id, now=NOW)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(issue, (first.id, second.id)))

    states = {
        _state_after(store_factory(), first.id),
        _state_after(store_factory(), second.id),
    }
    assert states == {"issued", "superseded"}


def _state_after(store: SqlAlchemyIdentityStore, attempt_id: UUID) -> str:
    attempt = store.attempt(attempt_id)
    assert attempt is not None
    return attempt.state


def test_authorization_activity_and_audit_commit_and_rollback_together(
    store_factory: Callable[[], SqlAlchemyIdentityStore],
) -> None:
    """Catches activity updates committing when their authorization audit rolls back."""

    import hashlib

    store = store_factory()
    user = ProductUser(
        uuid4(), "activity@example.com", created_at=NOW, status_changed_at=NOW
    )
    request = _request()
    attempt = MagicLinkAttempt(
        uuid4(), request.id, "product_user", None, user.id, state="consumed"
    )
    token = "activity-token"
    session = ProductSession(
        uuid4(), user.id, attempt.id, hashlib.sha256(token.encode()).digest(), NOW
    )
    with store.transaction():
        store.save_user(user)
        store.save_request(request)
        store.save_attempt(attempt)
        store.save_role(RoleAssignment(uuid4(), user.id, "user", NOW))
        store.save_session(session)

    activity_at = NOW + timedelta(minutes=1)
    AccessControl(store).authorize(
        token,
        action="auth.session.read",
        resource_owner_id=None,
        now=activity_at,
    )
    reader = store_factory()
    last_activity = reader.session_by_digest(session.token_digest)
    assert last_activity is not None
    assert last_activity.last_activity_at == activity_at
    assert reader.audit_events()[-1].event_type == "authorization.allowed.v1"
    before_audits = reader.audit_events()

    class FailingAuditAccessControl(AccessControl):
        def _audit(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("audit failure")

    with pytest.raises(RuntimeError, match="audit failure"):
        FailingAuditAccessControl(store_factory()).authorize(
            token,
            action="auth.session.read",
            resource_owner_id=None,
            now=NOW + timedelta(minutes=2),
        )

    rolled_back = store_factory()
    rolled_back_session = rolled_back.session_by_digest(session.token_digest)
    assert rolled_back_session is not None
    assert rolled_back_session.last_activity_at == activity_at
    assert rolled_back.audit_events() == before_audits
