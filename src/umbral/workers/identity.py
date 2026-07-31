"""Durable identity issue-job handler.

The queue payload contains only the attempt UUID and correlation metadata; the
worker reloads the email and current eligibility from the identity store.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from uuid import UUID

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.retention import purge_request_fingerprints
from umbral.application.jobs.contracts import JobContext, JsonScalar


class IdentityMagicLinkIssueHandler:
    job_type = "identity.magic_link.issue"

    def __init__(self, access: IdentityAccess) -> None:
        self.access = access

    def normalize_target(self, raw_target: str) -> str:
        return str(UUID(raw_target))

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        attempt_id = UUID(context.logical_target)
        self.access.issue_attempt(
            attempt_id,
            now=datetime.now(timezone.utc),
            correlation_id=context.correlation_id,
        )
        return {"attempt_id": str(attempt_id), "result": "processed"}


class IdentityRetentionHandler:
    job_type = "identity.retention.purge"

    def __init__(self, access: IdentityAccess) -> None:
        self.access = access

    def normalize_target(self, raw_target: str) -> str:
        if raw_target != "identity":
            raise ValueError("identity retention target is fixed")
        return raw_target

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        del context
        purged = purge_request_fingerprints(
            self.access.store, now=datetime.now(timezone.utc)
        )
        return {"purged_requests": purged, "result": "processed"}
