"""Private-beta magic-link flow tests across the application and database seams."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from tests.support.containers import ServiceConnection
from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.identity.contracts import IdentityError
from umbral.domain.identity.models import (
    AccessAuditEvent,
    ExternalIdentityLink,
    ProductUser,
)
from umbral.infrastructure.db.models.identity import (
    AccessAuditEvent as AccessAuditEventRow,
)
from umbral.infrastructure.db.models.identity import IdentityInvitation
from umbral.infrastructure.db.models.identity import (
    MagicLinkRequest as MagicLinkRequestRow,
)
from umbral.infrastructure.db.repositories.identity import (
    InMemoryIdentityStore,
    PostgresIdentityRepository,
)
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _new_access(
    email: str = "person@example.com",
) -> tuple[IdentityAccess, InMemoryIdentityStore, RecordingEmailAdapter]:
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation(email)
    mail = RecordingEmailAdapter()
    return IdentityAccess(store, FakeIdentityProvider(), mail), store, mail


def _issue(
    access: IdentityAccess,
    store: InMemoryIdentityStore,
    mail: RecordingEmailAdapter,
) -> tuple[object, str]:
    attempt_id = next(reversed(store.attempts))
    attempt = store.attempts[attempt_id]
    access.issue_attempt(attempt.id, now=NOW)
    capture_url = str(mail.messages[-1]["capture_url"])
    return attempt, capture_url.split("token_hash=", 1)[1]


def test_first_activation_creates_one_user_link_and_role() -> None:
    access, store, mail = _new_access()
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=NOW,
    )
    attempt, token_hash = _issue(access, store, mail)

    session = access.confirm_magic_link(
        attempt_id=attempt.id,
        token_hash=token_hash,
        now=NOW,
    )

    assert len(store.users) == len(store.links) == len(store.roles) == 1
    assert len(store.sessions) == 1
    assert session.user_id == next(iter(store.users))


def test_repeat_login_reuses_identity_and_creates_a_new_session() -> None:
    access, store, mail = _new_access()
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin-a",
        correlation_id=uuid4(),
        now=NOW,
    )
    first_attempt, first_hash = _issue(access, store, mail)
    first = access.confirm_magic_link(
        attempt_id=first_attempt.id,
        token_hash=first_hash,
        now=NOW,
    )

    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin-b",
        correlation_id=uuid4(),
        now=NOW,
    )
    second_attempt, second_hash = _issue(access, store, mail)
    second = access.confirm_magic_link(
        attempt_id=second_attempt.id,
        token_hash=second_hash,
        now=NOW,
    )

    assert second.user_id == first.user_id
    assert len(store.users) == len(store.links) == len(store.roles) == 1
    assert len(store.sessions) == 2


def test_identity_conflict_rolls_back_activation_and_audit() -> None:
    access, store, mail = _new_access()
    other = ProductUser(
        uuid4(), "other@example.com", created_at=NOW, status_changed_at=NOW
    )
    store.users[other.id] = other
    subject = "fake-subject-" + hashlib.sha256(b"person@example.com").hexdigest()[:24]
    store.links[uuid4()] = ExternalIdentityLink(
        uuid4(), other.id, "fake", "fake://local", subject, "other@example.com", NOW
    )
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=NOW,
    )
    attempt, token_hash = _issue(access, store, mail)
    users_before = set(store.users)
    audits_before = len(store.audits)

    with pytest.raises(IdentityError) as error:
        access.confirm_magic_link(attempt_id=attempt.id, token_hash=token_hash, now=NOW)

    assert error.value.code == "auth.access_denied"
    assert set(store.users) == users_before
    assert len(store.links) == 1
    assert len(store.sessions) == 0
    assert len(store.audits) == audits_before


def test_provider_failure_leaves_no_access_grant() -> None:
    access, store, mail = _new_access()
    provider = access.provider
    assert isinstance(provider, FakeIdentityProvider)
    provider.fail_generation = True
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=NOW,
    )
    attempt_id = next(iter(store.attempts))
    access.issue_attempt(attempt_id, now=NOW)

    assert store.attempts[attempt_id].state == "failed"
    assert not store.users and not store.links and not store.sessions
    assert not mail.messages


def test_ten_duplicate_confirmations_create_one_session() -> None:
    access, store, mail = _new_access()
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=NOW,
    )
    attempt, token_hash = _issue(access, store, mail)
    outcomes: list[str] = []
    for _ in range(10):
        try:
            access.confirm_magic_link(
                attempt_id=attempt.id, token_hash=token_hash, now=NOW
            )
        except IdentityError as error:
            outcomes.append(error.code)

    assert len(store.sessions) == 1
    assert outcomes == ["auth.link_unavailable"] * 9


class _FailingAuditAccess(IdentityAccess):
    def _audit(self, *args: object, **kwargs: object) -> None:
        raise RuntimeError("audit sink unavailable")


def test_application_transaction_rolls_back_request_and_audit() -> None:
    store = InMemoryIdentityStore()
    access = _FailingAuditAccess(store, FakeIdentityProvider(), RecordingEmailAdapter())

    with pytest.raises(RuntimeError, match="audit sink unavailable"):
        access.request_magic_link(
            email="person@example.com",
            origin_fingerprint="origin",
            correlation_id=uuid4(),
            now=NOW,
        )

    assert store.requests == {}
    assert store.attempts == {}
    assert store.audits == []


def _migrated_session(connection: ServiceConnection) -> Session:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    return Session(engine)


def test_postgres_invitation_preload_and_rate_limit(
    postgres_container: ServiceConnection,
) -> None:
    session = _migrated_session(postgres_container)
    try:
        invitation = IdentityInvitation(
            normalized_email="person@example.com",
            status="active",
            preload_actor_kind="operator",
            preload_actor_id="test",
            preload_source="integration",
            created_at=NOW,
            updated_at=NOW,
            source="test",
            correlation_id=uuid4(),
        )
        session.add(invitation)
        session.commit()
        assert session.scalar(
            select(IdentityInvitation).where(
                IdentityInvitation.normalized_email == "person@example.com"
            )
        ) is not None

        repository = PostgresIdentityRepository(session)
        email_fingerprint = b"e" * 32
        origin_fingerprint = b"o" * 32
        allowed = [
            repository.reserve_request(
                email_fingerprint=email_fingerprint,
                origin_fingerprint=origin_fingerprint,
                email_limit=3,
                origin_limit=20,
                correlation_id=uuid4(),
                decision="eligible",
            )
            for _ in range(4)
        ]
        session.commit()
        assert allowed == [True, True, True, False]
        assert (
            session.scalar(select(func.count()).select_from(MagicLinkRequestRow)) == 4
        )
    finally:
        engine = session.get_bind()
        session.close()
        engine.dispose()


def test_postgres_transaction_rolls_back_request_and_audit(
    postgres_container: ServiceConnection,
) -> None:
    session = _migrated_session(postgres_container)
    request_id = uuid4()
    event_id = uuid4()
    try:
        with pytest.raises(RuntimeError, match="force rollback"):
            with session.begin():
                session.add(
                    MagicLinkRequestRow(
                        id=request_id,
                        email_fingerprint=b"e" * 32,
                        origin_fingerprint=b"o" * 32,
                        decision="eligible",
                        requested_at=NOW,
                        purge_after=NOW,
                        correlation_id=uuid4(),
                    )
                )
                PostgresIdentityRepository(session).append_audit(
                    AccessAuditEvent(
                        event_id,
                        "magic_link.requested.v1",
                        "accepted",
                        "eligible",
                        uuid4(),
                        NOW,
                        request_id=request_id,
                    )
                )
                raise RuntimeError("force rollback")

        assert session.scalar(
            select(func.count())
            .select_from(MagicLinkRequestRow)
            .where(MagicLinkRequestRow.id == request_id)
        ) == 0
        assert session.scalar(
            select(func.count())
            .select_from(AccessAuditEventRow)
            .where(AccessAuditEventRow.id == event_id)
        ) == 0
    finally:
        engine = session.get_bind()
        session.close()
        engine.dispose()
