"""Regression coverage for explicit request-attempt persistence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.application.jobs.contracts import JobSnapshot, SubmitJob
from umbral.domain.identity.models import MagicLinkAttempt
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider


class _CopyingStore(InMemoryIdentityStore):
    """Adapter double that requires every mutated record to be saved again."""

    def save_attempt(self, attempt: MagicLinkAttempt) -> None:
        super().save_attempt(deepcopy(attempt))

    def attempt(self, attempt_id: UUID) -> MagicLinkAttempt | None:
        attempt = super().attempt(attempt_id)
        return deepcopy(attempt) if attempt is not None else None


class _CapturingRuntime:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.logical_target: str | None = None
        self.execution_id = uuid4()

    def submit(self, command: SubmitJob) -> JobSnapshot:
        self.logical_target = command.identity.logical_target
        if self.fail:
            raise RuntimeError("queue unavailable")
        return JobSnapshot(
            execution_id=self.execution_id,
            identity=command.identity,
            state="queued",  # type: ignore[arg-type]
            attempt_count=0,
            max_attempts=5,
            result=None,
            error_code=None,
            available_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def _attempt_after_request(
    *, fail_submit: bool
) -> tuple[MagicLinkAttempt, _CapturingRuntime]:
    store = _CopyingStore()
    AccessAdministration(store).preload_invitation("person@example.com")
    runtime = _CapturingRuntime(fail=fail_submit)
    IdentityAccess(
        store,
        FakeIdentityProvider(),
        RecordingEmailAdapter(),
        job_runtime=runtime,  # type: ignore[arg-type]
    ).request_magic_link(
        email="person@example.com",
        origin_fingerprint="origin",
        correlation_id=uuid4(),
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert runtime.logical_target is not None
    attempt = store.attempt(UUID(runtime.logical_target))
    assert attempt is not None
    return attempt, runtime


def test_request_persists_job_execution_assignment_with_copying_adapter() -> None:
    """Catches mutating the attempt after save without persisting the assignment."""

    attempt, runtime = _attempt_after_request(fail_submit=False)

    assert attempt.job_execution_id == runtime.execution_id
    assert attempt.state == "pending"


def test_request_persists_failed_job_submission_with_copying_adapter() -> None:
    """Catches losing the failed state when a job runtime rejects submission."""

    attempt, _ = _attempt_after_request(fail_submit=True)

    assert attempt.state == "failed"
    assert attempt.failure_reason == "job_submission_failed"
