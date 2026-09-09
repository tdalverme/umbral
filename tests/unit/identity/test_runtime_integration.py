from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tests.fakes.transactions import InMemoryTransactionManager
from tests.support.identity import requested_attempt
from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.jobs.contracts import JobSnapshot, SubmitJob
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.domain.identity.models import Invitation
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue
from umbral.workers.registry import build_identity_registry


class _DeferredRelayRuntime:
    def __init__(self, *, commits: InMemoryTransactionManager) -> None:
        self.commits = commits
        self.execution_id = uuid4()
        self.submit_relay_flags: list[bool | None] = []
        self.relays: list[tuple[int, object]] = []

    def submit(
        self, command: SubmitJob, *, immediate_relay: bool | None = None
    ) -> JobSnapshot:
        self.submit_relay_flags.append(immediate_relay)
        return JobSnapshot(
            execution_id=self.execution_id,
            identity=command.identity,
            state="pending",  # type: ignore[arg-type]
            attempt_count=0,
            max_attempts=5,
            result=None,
            error_code=None,
            available_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def relay_due(
        self, *, limit: int, execution_id: object | None = None
    ) -> object:
        self.relays.append((self.commits.commits, execution_id))
        assert limit == 1
        return object()


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


def test_identity_request_defers_immediate_relay_until_attempt_is_committed() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    transaction_manager = InMemoryTransactionManager()
    runtime = _DeferredRelayRuntime(commits=transaction_manager)
    access = IdentityAccess(
        store,
        FakeIdentityProvider(),
        RecordingEmailAdapter(),
        transaction_manager=transaction_manager,
        job_runtime=runtime,  # type: ignore[arg-type]
    )

    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=now,
    )

    assert runtime.submit_relay_flags == [False]
    assert runtime.relays == [(1, runtime.execution_id)]


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
