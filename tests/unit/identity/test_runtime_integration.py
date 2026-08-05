from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tests.fakes.transactions import InMemoryTransactionManager
from tests.support.identity import requested_attempt
from umbral.application.identity.access import IdentityAccess
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.domain.identity.models import Invitation
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.workers.registry import build_identity_registry


def test_identity_request_commits_attempt_job_and_audit_with_one_correlation() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    correlation_id = uuid4()
    store = InMemoryIdentityStore()
    invitation = Invitation.new("person@example.com")
    store.save_invitation(invitation)
    transaction_manager = InMemoryTransactionManager()
    runtime = InMemoryJobRuntime(queue=RecordingJobQueue())
    access = IdentityAccess(
        store,
        FakeIdentityProvider(),
        RecordingEmailAdapter(),
        transaction_manager=transaction_manager,
        job_runtime=runtime,
    )

    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=correlation_id,
        now=now,
    )

    attempt = requested_attempt(access, store)
    submission = runtime.submissions[0]
    assert transaction_manager.commits == 1
    assert transaction_manager.rollbacks == 0
    assert attempt.job_execution_id == submission.execution_id
    assert submission.identity.logical_target == str(attempt.id)
    assert runtime.correlation_id(submission.execution_id) == correlation_id
    request = store.request(attempt.request_id)
    assert request is not None and request.correlation_id == correlation_id
    assert all(event.correlation_id == correlation_id for event in store.audit_events())


def test_identity_worker_registry_exposes_reference_only_handlers() -> None:
    access = IdentityAccess(
        InMemoryIdentityStore(),
        FakeIdentityProvider(),
        RecordingEmailAdapter(),
    )

    registry = build_identity_registry(access)

    assert registry.types() == (
        "identity.magic_link.issue",
        "identity.retention.purge",
    )
    assert set(registry.as_mapping()) == set(registry.types())
