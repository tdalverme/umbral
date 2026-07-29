"""Retention operation for minimized rate-limit evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from umbral.application.identity.ports import IdentityStore


def purge_request_fingerprints(store: IdentityStore, *, now: datetime) -> int:
    cutoff = now.astimezone(timezone.utc)
    expired = [
        key for key, item in store.requests.items() if item.purge_after <= cutoff
    ]
    for key in expired:
        del store.requests[key]
    return len(expired)
