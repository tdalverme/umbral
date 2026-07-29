"""Sentry initialization with PII and attachment collection disabled."""

from __future__ import annotations

from typing import cast

import sentry_sdk
from sentry_sdk.types import Event, Hint

from umbral.infrastructure.observability.filtering import filter_sentry_event


def _before_send(event: Event, hint: Hint) -> Event | None:
    return cast(Event | None, filter_sentry_event(event, hint))


def initialize_sentry(dsn: str | None, release: str) -> None:
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        release=release,
        send_default_pii=False,
        attach_stacktrace=False,
        before_send=_before_send,
    )
