"""Application contracts and services for durable background jobs."""

from .contracts import (
    JobContext,
    JobIdentity,
    JobSnapshot,
    JobState,
    PermanentJobError,
    SubmitJob,
    TransientJobError,
    classify_failure,
)

__all__ = [
    "JobContext",
    "JobIdentity",
    "JobSnapshot",
    "JobState",
    "PermanentJobError",
    "SubmitJob",
    "TransientJobError",
    "classify_failure",
]
