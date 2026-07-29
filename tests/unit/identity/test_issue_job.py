from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from umbral.application.identity.access import IdentityAccess
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.domain.identity.models import Invitation
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider
from umbral.infrastructure.queue.recording_queue import RecordingJobQueue


def test_eligible_request_submits_only_attempt_reference() -> None:
    store = InMemoryIdentityStore()
    invitation = Invitation.new("person@example.com")
    store.invitations[invitation.id] = invitation
    queue = RecordingJobQueue()
    runtime = InMemoryJobRuntime(queue=queue)
    access = IdentityAccess(
        store,
        FakeIdentityProvider(),
        RecordingEmailAdapter(),
        job_runtime=runtime,
    )
    access.request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert len(runtime.submissions) == 1
    assert queue.messages[0].payload.keys() == {
        "execution_id",
        "attempt_number",
        "correlation_id",
    }
