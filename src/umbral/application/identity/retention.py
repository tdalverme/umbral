"""Retention operation for minimized rate-limit evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from umbral.application.identity.ports import IdentityStore


def purge_request_fingerprints(store: IdentityStore, *, now: datetime) -> int:
    cutoff = now.astimezone(timezone.utc)
    with store.transaction():
        return store.purge_requests_before(cutoff)
