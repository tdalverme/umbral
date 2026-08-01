"""Sentry initialization with PII and attachment collection disabled."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

import sentry_sdk
from sentry_sdk.types import Event, Hint

from umbral.infrastructure.observability.filtering import filter_sentry_event


def _before_send(event: Event, hint: Hint) -> Event | None:
    return cast(Event | None, filter_sentry_event(event, hint))


def _before_send_transaction(event: Event, hint: Hint) -> Event | None:
    return cast(Event | None, filter_sentry_event(event, hint))


def initialize_sentry(
    dsn: str | None,
    release: str,
    *,
    initializer: Callable[..., Any] = sentry_sdk.init,
) -> bool:
    """Configure Sentry once by the runtime without exposing provider errors."""

    if not dsn:
        return True
    try:
        initializer(
            dsn=dsn,
            release=release,
            send_default_pii=False,
            attach_stacktrace=False,
            before_send=_before_send,
            before_send_transaction=_before_send_transaction,
        )
    except Exception:
        return False
    return True
