from __future__ import annotations

from datetime import datetime, timezone

import pytest

from umbral.application.jobs.contracts import (
    JobIdentity,
    JobState,
    PermanentJobError,
    TransientJobError,
    UnclassifiedJobError,
    classify_failure,
    is_terminal_state,
    normalize_target,
)


def test_normalize_target_is_stable_and_rejects_empty_or_secret_bearing_values() -> (
    None
):
    assert normalize_target("  ref:ABC-123  ") == "ref:ABC-123"

    with pytest.raises(ValueError, match="target"):
        normalize_target("   ")
    with pytest.raises(ValueError, match="target"):
        normalize_target("https://example.test/?token=secret")


def test_job_identity_is_composed_from_normalized_components() -> None:
    identity = JobIdentity.create(
        " Foundation.Reference ", " ref:ABC-123 ", " request-42 "
    )

    assert identity.job_type == "foundation.reference"
    assert identity.logical_target == "ref:ABC-123"
    assert identity.idempotency_key == "request-42"
    assert identity.key == ("foundation.reference", "ref:ABC-123", "request-42")


def test_terminal_states_are_succeeded_and_failed_only() -> None:
    assert is_terminal_state(JobState.SUCCEEDED)
    assert is_terminal_state(JobState.FAILED)
    assert not is_terminal_state(JobState.PENDING)
    assert not is_terminal_state("running")


@pytest.mark.parametrize(
    ("error", "expected_code", "expected_kind"),
    [
        (TransientJobError("provider.timeout"), "provider.timeout", "transient"),
        (PermanentJobError("input.invalid"), "input.invalid", "permanent"),
        (
            RuntimeError("credentials=do-not-persist"),
            "job.unclassified_failure",
            "unclassified",
        ),
    ],
)
def test_failure_classification_is_sanitized(
    error: Exception, expected_code: str, expected_kind: str
) -> None:
    classified = classify_failure(error)

    assert classified.code == expected_code
    assert classified.kind == expected_kind
    assert "credentials" not in classified.code
    assert isinstance(classified.occurred_at, datetime)
    assert classified.occurred_at.tzinfo == timezone.utc


def test_unclassified_error_is_not_retryable() -> None:
    classified = classify_failure(UnclassifiedJobError("stack trace"))
    assert classified.kind == "unclassified"
    assert not classified.retryable
