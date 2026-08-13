# ruff: noqa: E501
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from tests.support.identity import access_with_recording_jobs, requested_attempt
from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.jobs.service import InMemoryJobRuntime
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider


class _AttemptSaveSpy(InMemoryIdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.attempt_save_calls = 0

    def save_attempt(self, attempt: object) -> None:
        self.attempt_save_calls += 1
        super().save_attempt(attempt)  # type: ignore[arg-type]


def _service() -> tuple[IdentityAccess, _AttemptSaveSpy]:
    store = _AttemptSaveSpy()
    AccessAdministration(store).preload_invitation("person@example.com")
    return access_with_recording_jobs(store, FakeIdentityProvider(), RecordingEmailAdapter()), store


def test_email_limit_is_exact_and_does_not_create_attempt() -> None:
    service, store = _service()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for _ in range(3):
        service.request_magic_link(
            email="person@example.com",
            origin_fingerprint="same",
            correlation_id=uuid4(),
            now=now,
        )
    third = requested_attempt(service, store)
    runtime = service.job_runtime
    assert isinstance(runtime, InMemoryJobRuntime)
    submissions_before = len(runtime.submissions)
    attempts_before = store.attempt_save_calls
    service.request_magic_link(
        email="person@example.com",
        origin_fingerprint="same",
        correlation_id=uuid4(),
        now=now,
    )
    assert len(runtime.submissions) == submissions_before
    assert store.attempt_save_calls == attempts_before
    assert requested_attempt(service, store) == third
    assert store.audit_events()[-1].reason == "email_rate_limited"
    service.request_magic_link(
        email="person@example.com",
        origin_fingerprint="same",
        correlation_id=uuid4(),
        now=now + timedelta(minutes=15, seconds=1),
    )
    assert requested_attempt(service, store) != third


# ruff: noqa: E501
