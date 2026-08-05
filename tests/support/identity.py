"""Identity test composition through public application seams."""

from __future__ import annotations

from uuid import UUID

from umbral.application.identity.access import IdentityAccess
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.domain.identity.models import MagicLinkAttempt
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue


def access_with_recording_jobs(
    store: InMemoryIdentityStore,
    provider: FakeIdentityProvider,
    email: RecordingEmailAdapter,
) -> IdentityAccess:
    return IdentityAccess(
        store,
        provider,
        email,
        job_runtime=InMemoryJobRuntime(queue=RecordingJobQueue()),
    )


def requested_attempt(
    access: IdentityAccess, store: InMemoryIdentityStore
) -> MagicLinkAttempt:
    runtime = access.job_runtime
    assert isinstance(runtime, InMemoryJobRuntime)
    attempt_id = UUID(runtime.submissions[-1].identity.logical_target)
    attempt = store.attempt(attempt_id)
    assert attempt is not None
    return attempt
