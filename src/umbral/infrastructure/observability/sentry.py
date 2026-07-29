"""Sentry initialization with PII and attachment collection disabled."""

from __future__ import annotations

import sentry_sdk

from umbral.infrastructure.observability.filtering import filter_sentry_event


def initialize_sentry(dsn: str | None, release: str) -> None:
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        release=release,
        send_default_pii=False,
        attach_stacktrace=False,
        before_send=filter_sentry_event,
    )
