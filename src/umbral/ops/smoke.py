"""Provider-neutral release and identity smoke checks."""
# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, cast
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

REQUIRED_SURFACES = ("web", "api", "worker", "scheduler")
_SHA256 = "0123456789abcdef"


@dataclass(frozen=True, slots=True)
class PreviewHttpResponse:
    """Minimal, injected public-BFF response used by the remote smoke."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class ObservedPreviewMessage:
    """Private mailbox observation; its capture URL must never leave this module."""

    message_id: str
    capture_url: str
    correlation_id: UUID


class PreviewSmokeObserver:
    """Operator-only boundary for invitation and provider observations."""

    def preload_invitation(self) -> str:
        raise NotImplementedError

    def runtime_surfaces(self, *, timeout_seconds: int) -> tuple[dict[str, str], ...]:
        raise NotImplementedError

    def wait_for_magic_link(
        self,
        correlation_id: UUID,
        *,
        recipient: str,
        requested_at: datetime,
        timeout_seconds: int,
    ) -> ObservedPreviewMessage:
        raise NotImplementedError

    def trigger_delivery_event(self, scenario: str, correlation_id: UUID) -> str:
        raise NotImplementedError

    def prepare_delivery_recipient(self, scenario: str, correlation_id: UUID) -> str:
        raise NotImplementedError

    def cleanup_delivery_recipient(self, recipient: str) -> None:
        raise NotImplementedError

    def audit_projection_observed(
        self, provider_event_id: str, *, timeout_seconds: int
    ) -> bool:
        raise NotImplementedError

    def wait_for_no_magic_link(
        self,
        correlation_id: UUID,
        *,
        recipient: str,
        requested_at: datetime,
        timeout_seconds: int,
    ) -> bool:
        raise NotImplementedError

    def backdate_session(self, user_id: UUID, *, timeout_seconds: int) -> bool:
        raise NotImplementedError

    def evidence_text(self) -> object:
        raise NotImplementedError


class ResendPreviewObserver(PreviewSmokeObserver):
    """Injected Resend REST observer; credentials stay inside this boundary."""

    def __init__(
        self,
        *,
        observation_token: str,
        resend_get: Callable[[str, str], object],
        preload: Callable[[], str],
        event_trigger: Callable[[str, UUID], str],
        audit_projection: Callable[[str, int], bool],
    ) -> None:
        self._observation_token = observation_token
        self._resend_get = resend_get
        self._preload = preload
        self._event_trigger = event_trigger
        self._audit_projection = audit_projection
        self._observed_message_ids: set[str] = set()

    def preload_invitation(self) -> str:
        return self._preload()

    def wait_for_magic_link(
        self,
        correlation_id: UUID,
        *,
        recipient: str,
        requested_at: datetime,
        timeout_seconds: int,
    ) -> ObservedPreviewMessage:
        deadline = monotonic() + timeout_seconds
        while True:
            listing = self._resend_get("https://api.resend.com/emails", self._observation_token)
            if not isinstance(listing, Mapping) or not isinstance(listing.get("data"), list):
                raise ValueError("Resend email listing is invalid")
            matches = [item for item in listing["data"] if _resend_message_matches(item, recipient, requested_at, correlation_id)]
            if len(matches) > 1:
                raise ValueError("Resend message correlation is ambiguous")
            if len(matches) == 1 and isinstance(matches[0], Mapping) and isinstance(matches[0].get("id"), str):
                message_id = matches[0]["id"]
                if message_id not in self._observed_message_ids:
                    detail = self._resend_get(f"https://api.resend.com/emails/{message_id}", self._observation_token)
                    capture_url = _capture_url_from_resend_detail(detail)
                    if capture_url:
                        self._observed_message_ids.add(message_id)
                        return ObservedPreviewMessage(message_id, capture_url, correlation_id)
            _sleep_remaining(deadline)

    def trigger_delivery_event(self, scenario: str, correlation_id: UUID) -> str:
        if scenario not in {"delivered", "bounced", "complained"}:
            raise ValueError("unknown Resend test event")
        return self._event_trigger(scenario, correlation_id)

    def audit_projection_observed(
        self, provider_event_id: str, *, timeout_seconds: int
    ) -> bool:
        return self._audit_projection(provider_event_id, timeout_seconds)

    def evidence_text(self) -> object:
        return {"observer": "injected", "messages": sorted(self._observed_message_ids)}

    def wait_for_no_magic_link(
        self,
        correlation_id: UUID,
        *,
        recipient: str,
        requested_at: datetime,
        timeout_seconds: int,
    ) -> bool:
        del correlation_id, recipient, requested_at, timeout_seconds
        raise NotImplementedError("injected observer must prove provider absence")

    def backdate_session(self, user_id: UUID, *, timeout_seconds: int) -> bool:
        del user_id, timeout_seconds
        raise NotImplementedError("injected observer must backdate operator-side")


class BuiltInPreviewObserver(PreviewSmokeObserver):
    """Preview-only composition for Resend observation and operator DB checks."""

    def __init__(
        self,
        *,
        database_url: str,
        observation_token: str,
        sender: str,
        redis_url: str = "",
        deadline: float | None = None,
    ) -> None:
        self._database_url = database_url
        self._observation_token = observation_token
        self._sender = sender
        self._redis_url = redis_url
        self._deadline = deadline
        self._event_correlations: dict[str, UUID] = {}
        self._delivery_reasons: dict[UUID, str] = {}
        self._evidence: list[dict[str, object]] = []

    def preload_invitation(self) -> str:
        raise RuntimeError("preview preload is performed before the smoke process")

    def runtime_surfaces(self, *, timeout_seconds: int) -> tuple[dict[str, str], ...]:
        deadline = self._start_deadline(timeout_seconds)
        import psycopg

        with psycopg.connect(
            self._database_url, connect_timeout=max(1, int(_remaining(deadline)))
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT surface, state, release_id, manifest_sha256, artifact_digest, correlation_id, observed_at "
                    "FROM runtime_surface_status WHERE environment = 'preview' "
                    "AND observed_at >= NOW() - INTERVAL '10 minutes'"
                )
                rows = cursor.fetchall()
        return tuple(
            {
                "surface": str(surface),
                "state": str(state),
                "release_id": str(release_id),
                "manifest_sha256": str(checksum),
                "artifact_digest": str(digest),
                "correlation_id": str(correlation_id),
                "observed_at": _utc(observed_at).isoformat(),
            }
            for surface, state, release_id, checksum, digest, correlation_id, observed_at in rows
        )

    def wait_for_magic_link(
        self,
        correlation_id: UUID,
        *,
        recipient: str,
        requested_at: datetime,
        timeout_seconds: int,
    ) -> ObservedPreviewMessage:
        deadline = self._start_deadline(timeout_seconds)
        self.relay_pending(correlation_id)
        try:
            while True:
                listing = self._resend_json("GET", "/emails", None, deadline)
                messages = listing.get("data")
                if isinstance(messages, list):
                    matches = [
                        item
                        for item in messages
                        if _resend_message_matches(
                            item, recipient, requested_at, correlation_id
                        )
                    ]
                    if len(matches) == 1 and isinstance(matches[0], Mapping):
                        message_id = matches[0].get("id")
                        if isinstance(message_id, str):
                            detail = self._resend_json(
                                "GET", f"/emails/{message_id}", None, deadline
                            )
                            capture_url = _capture_url_from_resend_detail(detail)
                            if capture_url:
                                self._event_correlations[message_id] = correlation_id
                                return ObservedPreviewMessage(
                                    message_id, capture_url, correlation_id
                                )
                    if len(matches) > 1:
                        print(
                            f"SMOKE RESEND ambiguous matches={len(matches)}",
                            file=sys.stderr,
                        )
                        raise ValueError("Resend message correlation is ambiguous")
                else:
                    print(
                        f"SMOKE RESEND listing unexpected data={type(messages).__name__}",
                        file=sys.stderr,
                    )
                _sleep_remaining(deadline)
        except TimeoutError:
            self._print_attempt_state(correlation_id)
            raise

    def _print_attempt_state(self, correlation_id: UUID) -> None:
        import psycopg

        try:
            with psycopg.connect(self._database_url, connect_timeout=5) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT a.state, a.failure_reason, a.provider_message_id, "
                        "r.decision, j.state, j.error_code "
                        "FROM magic_link_attempts a "
                        "LEFT JOIN magic_link_requests r ON r.id = a.request_id "
                        "LEFT JOIN job_executions j ON j.id = a.job_execution_id "
                        "WHERE r.correlation_id = %s",
                        (str(correlation_id),),
                    )
                    rows = cursor.fetchall()
            print(f"SMOKE RESEND attempt state rows={rows!r}", file=sys.stderr)
        except Exception as error:
            print(
                f"SMOKE RESEND attempt query failed: {type(error).__name__}: {error}",
                file=sys.stderr,
            )

    def relay_pending(self, correlation_id: UUID) -> None:
        """Publish this correlation's durable outbox messages to the job queue.

        The deployed scheduler only relays on its cron cadence, which can be
        minutes after a magic-link request; the smoke relays the pending outbox
        directly so the worker issues the email promptly.
        """

        from redis import Redis
        from rq import Queue
        from rq.serializers import JSONSerializer

        if not self._redis_url:
            return
        import psycopg

        queue = Queue(
            "umbral",
            connection=Redis.from_url(self._redis_url),
            serializer=JSONSerializer(),
        )
        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT e.id, o.attempt_number, e.correlation_id "
                    "FROM job_outbox_messages o "
                    "JOIN job_executions e ON e.id = o.execution_id "
                    "WHERE e.correlation_id = %s AND o.state = 'pending'",
                    (str(correlation_id),),
                )
                rows = cursor.fetchall()
        for execution_id, attempt_number, execution_correlation_id in rows:
            queue.enqueue(
                "umbral.workers.worker:run_message",
                execution_id=str(execution_id),
                attempt_number=int(attempt_number),
                correlation_id=str(execution_correlation_id),
                job_id=f"{execution_id}-{attempt_number}",
            )

    def trigger_delivery_event(self, scenario: str, correlation_id: UUID) -> str:
        if scenario not in {"delivered", "bounced", "complained"}:
            raise ValueError("unknown Resend test event")
        deadline = self._require_deadline()
        recipient = f"{scenario}+{correlation_id.hex[:16]}@resend.dev"
        response = self._resend_json(
            "POST",
            "/emails",
            {
                "from": self._sender,
                "to": [recipient],
                "subject": f"Umbral preview {correlation_id}",
                "text": "preview provider event",
                "tags": [{"name": "correlation_id", "value": str(correlation_id)}],
            },
            deadline,
        )
        event_id = response.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("Resend event ID is unavailable")
        self._event_correlations[event_id] = correlation_id
        return event_id

    def prepare_delivery_recipient(self, scenario: str, correlation_id: UUID) -> str:
        if scenario not in {"delivered", "bounced", "complained"}:
            raise ValueError("unknown Resend test event")
        recipient = f"{scenario}+{correlation_id.hex[:16]}@resend.dev"
        from umbral.ops.identity import _preload_with_database

        _preload_with_database(recipient, self._database_url)
        self._event_correlations[recipient] = correlation_id
        self._delivery_reasons[correlation_id] = f"email_{scenario}"
        return recipient

    def cleanup_delivery_recipient(self, recipient: str) -> None:
        import psycopg

        with psycopg.connect(self._database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH target AS (
                        SELECT id FROM identity_invitations
                        WHERE normalized_email = %s AND status = 'active'
                    ),
                    attempts AS (
                        SELECT id FROM magic_link_attempts
                        WHERE invitation_id IN (SELECT id FROM target)
                    ),
                    requests AS (
                        SELECT id FROM magic_link_requests
                        WHERE id IN (
                            SELECT request_id FROM magic_link_attempts
                            WHERE invitation_id IN (SELECT id FROM target)
                        )
                    )
                    DELETE FROM access_audit_events
                    WHERE invitation_id IN (SELECT id FROM target)
                       OR attempt_id IN (SELECT id FROM attempts)
                       OR request_id IN (SELECT id FROM requests)
                    """,
                    (recipient,),
                )
                cursor.execute(
                    "DELETE FROM magic_link_attempts "
                    "WHERE invitation_id IN (SELECT id FROM identity_invitations "
                    "WHERE normalized_email = %s AND status = 'active')",
                    (recipient,),
                )
                cursor.execute(
                    "DELETE FROM identity_invitations "
                    "WHERE normalized_email = %s AND status = 'active'",
                    (recipient,),
                )
            connection.commit()

    def audit_projection_observed(
        self, provider_event_id: str, *, timeout_seconds: int
    ) -> bool:
        deadline = self._start_deadline(timeout_seconds)
        import psycopg

        while True:
            with psycopg.connect(
                self._database_url, connect_timeout=max(1, int(_remaining(deadline)))
            ) as connection:
                with connection.cursor() as cursor:
                    correlation_id = self._event_correlations.get(provider_event_id)
                    if correlation_id is None:
                        raise ValueError("unknown Resend provider message")
                    expected_reason = self._delivery_reasons.get(correlation_id)
                    cursor.execute(
                        "SELECT provider_event_id, event_type, reason, COUNT(*) "
                        "FROM access_audit_events WHERE provider = 'resend' "
                        "AND correlation_id = %s GROUP BY provider_event_id, event_type, reason",
                        (str(correlation_id),),
                    )
                    rows = cursor.fetchall()
            if (
                len(rows) == 1
                and rows[0][0]
                and rows[0][1] == "magic_link.delivery_observed.v1"
                and rows[0][2] == expected_reason
                and rows[0][3] == 1
            ):
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker

                from umbral.infrastructure.db.repositories.identity import (
                    SqlAlchemyIdentityStore,
                )
                from umbral.infrastructure.db.session import (
                    resolve_postgres_dialect_url,
                )

                engine = create_engine(resolve_postgres_dialect_url(self._database_url))
                try:
                    store = SqlAlchemyIdentityStore(sessionmaker(bind=engine))
                    with store.transaction():
                        if store.append_provider_audit_once("resend", str(rows[0][0]), None):
                            return False
                finally:
                    engine.dispose()
                return True
            _sleep_remaining(deadline)

    def wait_for_no_magic_link(
        self,
        correlation_id: UUID,
        *,
        recipient: str,
        requested_at: datetime,
        timeout_seconds: int,
    ) -> bool:
        deadline = min(self._start_deadline(timeout_seconds), monotonic() + 10)
        while True:
            if monotonic() >= deadline:
                return True
            listing = self._resend_json("GET", "/emails", None, deadline)
            messages = listing.get("data")
            if isinstance(messages, list) and any(
                _resend_message_matches(item, recipient, requested_at, correlation_id)
                for item in messages
            ):
                return False
            if monotonic() >= deadline:
                return True
            _sleep_remaining(deadline)

    def backdate_session(self, user_id: UUID, *, timeout_seconds: int) -> bool:
        deadline = self._start_deadline(timeout_seconds)
        import psycopg

        with psycopg.connect(
            self._database_url, connect_timeout=max(1, int(_remaining(deadline)))
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE product_sessions SET last_activity_at = NOW() - INTERVAL '31 minutes' "
                    "WHERE product_user_id = %s AND revoked_at IS NULL RETURNING id",
                    (str(user_id),),
                )
                changed = cursor.fetchone() is not None
            connection.commit()
        return changed

    def evidence_text(self) -> object:
        return {"operations": self._evidence, "events": list(self._event_correlations)}

    def _resend_json(
        self, method: str, path: str, payload: object | None, deadline: float
    ) -> Mapping[str, object]:
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        body = json.dumps(payload, separators=(",", ":")).encode() if payload else None
        request = Request(
            f"https://api.resend.com{path}",
            method=method,
            data=body,
            headers={
                "Authorization": f"Bearer {self._observation_token}",
                "Content-Type": "application/json",
                "User-Agent": "curl/8.7.1",
            },
        )
        try:
            with urlopen(request, timeout=_remaining(deadline)) as response:  # noqa: S310
                value = _json_object(response.read())
        except HTTPError as error:
            body = error.read()
            print(
                f"SMOKE RESEND {method} {path} HTTP {error.code} "
                f"body={body[:200]!r}",
                file=sys.stderr,
            )
            raise ValueError("Resend observation failed") from error
        return value

    def _start_deadline(self, timeout_seconds: int) -> float:
        deadline = monotonic() + timeout_seconds
        self._deadline = (
            deadline if self._deadline is None else min(self._deadline, deadline)
        )
        return self._deadline

    def _require_deadline(self) -> float:
        if self._deadline is None:
            raise ValueError("preview deadline is unavailable")
        return self._deadline


@dataclass(frozen=True, slots=True)
class PreviewSmokeConfig:
    """Private input to a bounded public-preview journey."""

    public_web_base_url: str
    release_id: str
    manifest_sha256: str
    artifact_digests: Mapping[str, str]
    invitation_id: str
    invited_email: str
    resend_observation_token: str
    timeout_seconds: int

    def __post_init__(self) -> None:
        parsed = urlparse(self.public_web_base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("preview smoke requires one public HTTPS web origin")
        if not self.release_id or len(self.release_id) > 100:
            raise ValueError("preview smoke requires a release ID")
        if not _is_sha256(self.manifest_sha256):
            raise ValueError("preview smoke requires a manifest checksum")
        if set(self.artifact_digests) != {"web", "runtime"} or not all(
            _is_digest(value) for value in self.artifact_digests.values()
        ):
            raise ValueError("preview smoke requires exact web and runtime digests")
        UUID(self.invitation_id)
        if not self.invited_email or not self.resend_observation_token:
            raise ValueError(
                "preview smoke requires private invitation and observation inputs"
            )
        if not 1 <= self.timeout_seconds <= 300:
            raise ValueError("preview smoke timeout must be bounded")


@dataclass(frozen=True, slots=True)
class PreviewSmokeCheck:
    scenario: str
    code: str
    provider_id: str | None
    correlation_id: UUID
    observed_at: datetime
    duration_ms: int

    @property
    def passed(self) -> bool:
        return self.code == "smoke.ok"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "scenario": self.scenario,
            "code": self.code,
            "correlation_id": str(self.correlation_id),
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "duration_ms": self.duration_ms,
        }
        payload["provider_id"] = self.provider_id
        return payload


@dataclass(frozen=True, slots=True)
class PreviewSmokeReport:
    checks: tuple[PreviewSmokeCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True, slots=True)
class SmokeCheck:
    name: str
    passed: bool
    code: str


@dataclass(frozen=True, slots=True)
class SmokeReport:
    checks: tuple[SmokeCheck, ...]
    product_data_used: bool = False

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def run_smoke(checks: Mapping[str, Callable[[], bool]]) -> SmokeReport:
    """Run a closed set of local checks and normalize failures."""

    required = (*REQUIRED_SURFACES, "extensions", "reference_job", "synthetic_object")
    results: list[SmokeCheck] = []
    for name in required:
        check = checks.get(name)
        if check is None:
            results.append(SmokeCheck(name, False, "smoke.missing_check"))
            continue
        try:
            passed = bool(check())
        except Exception:
            passed = False
        results.append(
            SmokeCheck(name, passed, "smoke.ok" if passed else "smoke.failed")
        )
    return SmokeReport(tuple(results))


def run_identity_smoke() -> dict[str, str]:
    from umbral.application.identity.access import IdentityAccess
    from umbral.application.identity.administration import AccessAdministration
    from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
    from umbral.infrastructure.email.recording import RecordingEmailAdapter
    from umbral.infrastructure.identity.fake import FakeIdentityProvider

    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("smoke@example.test")
    access = IdentityAccess(store, FakeIdentityProvider(), RecordingEmailAdapter())
    now = datetime.now(timezone.utc)
    access.request_magic_link(
        email="smoke@example.test",
        origin_fingerprint="smoke",
        correlation_id=uuid4(),
        now=now,
    )
    return {
        "result": "accepted",
        "sessions": str(store.session_count()),
        "synthetic": "true",
    }


def run_preview_identity_smoke(
    config: PreviewSmokeConfig,
    *,
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
    observer: PreviewSmokeObserver,
    now: Callable[[], datetime] | None = None,
    scanner_http: Callable[[str, str, bytes | None], PreviewHttpResponse] | None = None,
) -> PreviewSmokeReport:
    """Exercise the preview BFF while retaining all secret provider material locally."""

    clock = now or (lambda: datetime.now(timezone.utc))
    scanner = scanner_http or http
    checks: list[PreviewSmokeCheck] = []

    def check(
        scenario: str,
        operation: Callable[[], tuple[str | None, bool]],
    ) -> bool:
        started = monotonic()
        correlation_id = uuid4()
        provider_id: str | None = None
        try:
            provider_id, passed = operation()
        except Exception as error:
            print(
                f"SMOKE {scenario} RAISED {type(error).__name__}: {error}",
                file=sys.stderr,
            )
            passed = False
        checks.append(
            PreviewSmokeCheck(
                scenario=scenario,
                code="smoke.ok" if passed else "smoke.failed",
                provider_id=provider_id if passed else None,
                correlation_id=correlation_id,
                observed_at=_utc(clock()),
                duration_ms=max(0, round((monotonic() - started) * 1000)),
            )
        )
        return passed

    runtime_ok = check(
        "runtime_identity",
        lambda: (None, _runtime_identity_matches(config, http, observer)),
    )
    invitation_ok = check("invitation", lambda: (config.invitation_id, True))

    correlation_id = uuid4()
    message: ObservedPreviewMessage | None = None

    def request_invited() -> tuple[str | None, bool]:
        nonlocal message
        requested_at = clock()
        accepted = _request_magic_link(
            config, http, config.invited_email, correlation_id
        )
        message = observer.wait_for_magic_link(
            correlation_id,
            recipient=config.invited_email,
            requested_at=requested_at,
            timeout_seconds=config.timeout_seconds,
        )
        return message.message_id, accepted and message.correlation_id == correlation_id

    invited_ok = check("invited", request_invited)
    capture: tuple[str, str] | None = None
    if message is not None:
        try:
            capture = _capture_parameters(config, message.capture_url)
        except ValueError:
            capture = None

    scanner_ok = check(
        "scanner_prefetch",
        lambda: (
            message.message_id if message else None,
            capture is not None
            and message is not None
            and _public_response(scanner, "GET", message.capture_url, None).status_code
            == 303,
        ),
    )
    confirmation_ok = check(
        "explicit_confirmation",
        lambda: (
            message.message_id if message else None,
            capture is not None and _confirm_magic_link(config, http, *capture) == 204,
        ),
    )
    check(
        "single_use",
        lambda: (
            message.message_id if message else None,
            capture is not None and _confirm_magic_link(config, http, *capture) >= 400,
        ),
    )
    repeat_correlation = uuid4()
    repeat_requested_at: datetime | None = None
    repeat_capture: tuple[str, str] | None = None

    def request_repeat() -> tuple[str | None, bool]:
        nonlocal repeat_capture, repeat_requested_at
        repeat_requested_at = clock()
        accepted = _request_magic_link(
            config, http, config.invited_email, repeat_correlation
        )
        repeat_message = observer.wait_for_magic_link(
            repeat_correlation,
            recipient=config.invited_email,
            requested_at=repeat_requested_at,
            timeout_seconds=config.timeout_seconds,
        )
        try:
            repeat_capture = _capture_parameters(config, repeat_message.capture_url)
        except ValueError:
            repeat_capture = None
        return repeat_message.message_id, accepted and repeat_capture is not None and repeat_message.message_id != (message.message_id if message else "")

    check("repeat", request_repeat)
    non_invited_correlation = uuid4()

    def request_non_invited() -> tuple[str | None, bool]:
        requested_at = clock()
        email = _non_invited_email(config.invited_email)
        accepted = _request_magic_link(config, http, email, non_invited_correlation)
        absent = observer.wait_for_no_magic_link(
            non_invited_correlation,
            recipient=email,
            requested_at=requested_at,
            timeout_seconds=config.timeout_seconds,
        )
        return None, accepted and absent

    check(
        "non_invited",
        request_non_invited,
    )
    session: Mapping[str, object] | None = None

    def authorization() -> tuple[str | None, bool]:
        nonlocal session
        response = _public_response(
            http, "GET", _url(config, "/api/auth/session"), None
        )
        session = _json_object(response.body) if response.status_code == 200 else None
        return None, response.status_code == 200 and _is_uuid(
            str(session.get("user_id", ""))
        ) if session else False

    check("authorization", authorization)
    check(
        "logout",
        lambda: (
            None,
            _public_response(
                http, "POST", _url(config, "/api/auth/logout"), None
            ).status_code
            == 204
            and _public_response(http, "GET", _url(config, "/api/auth/session"), None).status_code == 401,
        ),
    )
    def idle_expiry() -> tuple[str | None, bool]:
        if repeat_capture is None or _confirm_magic_link(config, http, *repeat_capture) != 204:
            return None, False
        active = _public_response(http, "GET", _url(config, "/api/auth/session"), None)
        payload = _json_object(active.body) if active.status_code == 200 else {}
        user_id = payload.get("user_id")
        return None, isinstance(user_id, str) and observer.backdate_session(UUID(user_id), timeout_seconds=config.timeout_seconds) and _public_response(http, "GET", _url(config, "/api/auth/session"), None).status_code == 401

    check("idle_expiry", idle_expiry)
    for scenario in ("delivered", "bounced", "complained"):
        event_correlation = uuid4()

        def delivery_operation(
            scenario: str = scenario, correlation_id: UUID = event_correlation
        ) -> tuple[str | None, bool]:
            recipient = observer.prepare_delivery_recipient(scenario, correlation_id)
            try:
                requested_at = clock()
                accepted = _request_magic_link(config, http, recipient, correlation_id)
                message = observer.wait_for_magic_link(
                    correlation_id,
                    recipient=recipient,
                    requested_at=requested_at,
                    timeout_seconds=config.timeout_seconds,
                )
                observed = observer.audit_projection_observed(
                    message.message_id, timeout_seconds=config.timeout_seconds
                )
                return message.message_id, accepted and observed
            finally:
                observer.cleanup_delivery_recipient(recipient)

        check(
            scenario,
            delivery_operation,
        )
    check(
        "redaction",
        lambda: (
            None,
            _redaction_clean(
                observer.evidence_text(),
                config.invited_email,
                config.resend_observation_token,
                capture[1] if capture else "",
            ),
        ),
    )
    del runtime_ok, invitation_ok, invited_ok, scanner_ok, confirmation_ok
    return PreviewSmokeReport(tuple(checks))


def _runtime_identity_matches(
    config: PreviewSmokeConfig,
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
    observer: PreviewSmokeObserver,
) -> bool:
    health = _public_response(http, "GET", _url(config, "/health"), None)
    ready = _public_response(http, "GET", _url(config, "/ready"), None)
    version = _public_response(http, "GET", _url(config, "/version"), None)
    if (
        health.status_code != 200
        or ready.status_code != 200
        or version.status_code != 200
    ):
        print(
            f"SMOKE runtime_identity probes health={health.status_code} "
            f"ready={ready.status_code} version={version.status_code} "
            f"ready_body={ready.body[:200]!r}",
            file=sys.stderr,
        )
        return False
    health_payload = _json_object(health.body)
    ready_payload = _json_object(ready.body)
    version_payload = _json_object(version.body)
    identity = (
        health_payload == {"status": "alive"}
        and ready_payload.get("surface") == "web"
        and ready_payload.get("state") == "ready"
        and ready_payload.get("release_id") == config.release_id
        and version_payload.get("surface") == "web"
        and version_payload.get("release_id") == config.release_id
        and version_payload.get("manifest_sha256") == config.manifest_sha256
        and version_payload.get("artifact_digest") == config.artifact_digests["web"]
    )
    if not identity:
        print(
            f"SMOKE runtime_identity mismatch health={health_payload} "
            f"ready={ready_payload} version={version_payload}",
            file=sys.stderr,
        )
        return False
    return _runtime_surfaces_match(config, observer)


def _runtime_surfaces_match(
    config: PreviewSmokeConfig, observer: PreviewSmokeObserver
) -> bool:
    rows = observer.runtime_surfaces(timeout_seconds=config.timeout_seconds)
    if len(rows) != len(REQUIRED_SURFACES):
        print(
            f"SMOKE surfaces count rows={len(rows)} required={len(REQUIRED_SURFACES)} "
            f"surfaces={[row.get('surface') for row in rows]}",
            file=sys.stderr,
        )
        return False
    expected_digests = {
        "web": config.artifact_digests["web"],
        "api": config.artifact_digests["runtime"],
        "worker": config.artifact_digests["runtime"],
        "scheduler": config.artifact_digests["runtime"],
    }
    matches = {row.get("surface") for row in rows} == set(REQUIRED_SURFACES) and all(
        row.get("state") == "ready"
        and row.get("release_id") == config.release_id
        and row.get("manifest_sha256") == config.manifest_sha256
        and row.get("artifact_digest") == expected_digests[row["surface"]]
        and _is_uuid(row.get("correlation_id", ""))
        and _is_fresh_observed_at(row.get("observed_at"))
        for row in rows
    )
    if not matches:
        print(f"SMOKE surfaces mismatch rows={rows!r}", file=sys.stderr)
    return matches


def _is_fresh_observed_at(value: object) -> bool:
    try:
        observed_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - _utc(observed_at) <= timedelta(minutes=10)
    except (TypeError, ValueError):
        return False


def _operator_invitation(observer: PreviewSmokeObserver) -> str:
    invitation_id = observer.preload_invitation()
    return str(UUID(invitation_id))


def _request_magic_link(
    config: PreviewSmokeConfig,
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
    email: str,
    correlation_id: UUID,
) -> bool:
    response = _public_response(
        http,
        "POST",
        _url(config, "/api/auth/magic-link-requests"),
        ('{"email":"' + email + '"}').encode(),
        headers={"X-Correlation-ID": str(correlation_id)},
    )
    if response.status_code != 202:
        print(
            f"SMOKE magic-link POST status={response.status_code} "
            f"body={response.body[:200]!r}",
            file=sys.stderr,
        )
    return response.status_code == 202


def _capture_parameters(
    config: PreviewSmokeConfig, capture_url: str
) -> tuple[str, str]:
    parsed = urlparse(capture_url)
    if f"{parsed.scheme}://{parsed.netloc}" != config.public_web_base_url.rstrip("/"):
        raise ValueError("capture URL left the public web origin")
    query = parse_qs(parsed.query, strict_parsing=True)
    attempt_id = query.get("attempt_id", [""])[0]
    token_hash = query.get("token_hash", [""])[0]
    UUID(attempt_id)
    if not 32 <= len(token_hash) <= 512:
        raise ValueError("capture token is invalid")
    return attempt_id, token_hash


def _confirm_magic_link(
    config: PreviewSmokeConfig,
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
    attempt_id: str,
    token_hash: str,
) -> int:
    response = _public_response(
        http,
        "POST",
        _url(config, "/api/auth/confirmations"),
        (
            '{"attemptId":"' + attempt_id + '","tokenHash":"' + token_hash + '"}'
        ).encode(),
    )
    return response.status_code


def _delivery_event(
    observer: PreviewSmokeObserver,
    scenario: str,
    correlation_id: UUID,
    timeout_seconds: int,
) -> tuple[str | None, bool]:
    provider_event_id = observer.trigger_delivery_event(scenario, correlation_id)
    return provider_event_id, observer.audit_projection_observed(
        provider_event_id, timeout_seconds=timeout_seconds
    )


def _public_response(
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
    method: str,
    url: str,
    body: bytes | None,
    *,
    headers: Mapping[str, str] | None = None,
) -> PreviewHttpResponse:
    request = getattr(http, "request", None)
    if callable(request):
        return cast(PreviewHttpResponse, request(method, url, body, headers or {}))
    return http(method, url, body)


def _url(config: PreviewSmokeConfig, path: str) -> str:
    return config.public_web_base_url.rstrip("/") + path


def _json_object(body: bytes) -> Mapping[str, object]:
    import json

    payload = json.loads(body)
    if not isinstance(payload, Mapping):
        raise ValueError("response is not an object")
    return payload


def _capture_url_from_resend_detail(detail: object) -> str | None:
    if not isinstance(detail, Mapping):
        return None
    values = (detail.get("html"), detail.get("text"))
    for value in values:
        if not isinstance(value, str):
            continue
        match = re.search(r"https://[^\s\"'<>]+/auth/capture\?[^\s\"'<>]+", value)
        if match:
            return match.group(0)
    return None


def _resend_message_matches(
    item: object, recipient: str, requested_at: datetime, correlation_id: UUID
) -> bool:
    if not isinstance(item, Mapping):
        return False
    recipients = item.get("to")
    if isinstance(recipients, str):
        recipient_matches = recipients == recipient
    elif isinstance(recipients, list):
        recipient_matches = recipient in recipients
    else:
        recipient_matches = False
    created_at = item.get("created_at")
    try:
        created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    tags = item.get("tags")
    tag_values = (
        {
            str(tag.get("value"))
            for tag in tags
            if isinstance(tag, Mapping) and isinstance(tag.get("value"), str)
        }
        if isinstance(tags, list)
        else set()
    )
    subject = item.get("subject")
    return (
        recipient_matches
        and _utc(created) >= _utc(requested_at)
        and (str(correlation_id) in tag_values or str(correlation_id) in str(subject))
    )


def _non_invited_email(invited_email: str) -> str:
    local, separator, domain = invited_email.partition("@")
    if not separator:
        return "not-invited@example.invalid"
    return f"not-invited-{uuid4().hex[:12]}@{domain}"


def _redaction_clean(evidence: object, *canaries: str) -> bool:
    """Reject canaries at every nested evidence, log, and error value."""

    def values(value: object) -> list[str]:
        if isinstance(value, Mapping):
            return [
                *map(str, value.keys()),
                *(part for item in value.values() for part in values(item)),
            ]
        if isinstance(value, (list, tuple, set, frozenset)):
            return [part for item in value for part in values(item)]
        if isinstance(value, bytes):
            return [value.decode("utf-8", "replace")]
        return [str(value)]

    flattened = values(evidence)
    return all(
        not canary or all(canary not in value for value in flattened)
        for canary in canaries
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in _SHA256 for character in value)


def _is_digest(value: str) -> bool:
    return value.startswith("sha256:") and _is_sha256(value.removeprefix("sha256:"))


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("smoke timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _remaining(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("preview smoke timed out")
    return remaining


def _sleep_remaining(deadline: float) -> None:
    from time import sleep

    sleep(min(1.0, _remaining(deadline)))


def main(argv: list[str] | None = None) -> int:
    """Run the synthetic smoke locally or a preview journey with an injected observer."""

    parser = argparse.ArgumentParser(prog="python -m umbral.ops.smoke")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    subparsers.add_parser("local")
    preview = subparsers.add_parser("preview")
    preview.add_argument("--base-url", required=True)
    preview.add_argument("--manifest-path", required=True)
    preview.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    if args.mode == "local":
        print(json.dumps(run_identity_smoke(), separators=(",", ":")))
        return 0
    try:
        manifest = _json_object(open(args.manifest_path, "rb").read())  # noqa: PTH123
        config = PreviewSmokeConfig(
            public_web_base_url=args.base_url,
            release_id=_required_manifest_string(manifest, "release_id"),
            manifest_sha256=_manifest_sha256(args.manifest_path),
            artifact_digests=_manifest_digests(manifest),
            invitation_id=os.environ.get("UMBRAL_SMOKE_INVITATION_ID", ""),
            invited_email=os.environ.get("UMBRAL_SMOKE_INVITEE", ""),
            resend_observation_token=os.environ.get(
                "UMBRAL_SMOKE_RESEND_OBSERVATION_TOKEN", ""
            ),
            timeout_seconds=args.timeout_seconds,
        )
        deadline = monotonic() + config.timeout_seconds
        observer = _built_in_preview_observer(config, deadline=deadline)
        report = run_preview_identity_smoke(
            config,
            http=CookieHttpClient(deadline=deadline),
            scanner_http=CookieHttpClient(deadline=deadline, follow_redirects=False),
            observer=observer,
        )
    except Exception:
        print('{"passed":false,"code":"smoke.preview_unavailable"}')
        return 1
    print(json.dumps(report.to_dict(), separators=(",", ":")))
    return 0 if report.passed else 1


def _built_in_preview_observer(
    config: PreviewSmokeConfig, *, deadline: float | None = None
) -> PreviewSmokeObserver:
    database_url_name = os.environ.get("UMBRAL_SMOKE_OPERATOR_DATABASE_URL_ENV", "")
    database_url = os.environ.get(database_url_name, "")
    redis_url_name = os.environ.get("UMBRAL_SMOKE_OPERATOR_REDIS_URL_ENV", "")
    redis_url = os.environ.get(redis_url_name, "")
    sender = os.environ.get("RESEND_FROM_EMAIL", "")
    if not database_url_name or not database_url or not sender:
        raise ValueError("preview operator configuration is unavailable")
    return BuiltInPreviewObserver(
        database_url=database_url,
        observation_token=config.resend_observation_token,
        sender=sender,
        redis_url=redis_url,
        deadline=deadline,
    )


class CookieHttpClient:
    def __init__(
        self, *, deadline: float | None = None, follow_redirects: bool = True
    ) -> None:
        from http.cookiejar import CookieJar
        from urllib.request import (
            HTTPCookieProcessor,
            HTTPRedirectHandler,
            build_opener,
        )

        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, *args: object, **kwargs: object) -> None:
                del args, kwargs
                return None

        cookies = HTTPCookieProcessor(CookieJar())
        self._opener = (
            build_opener(cookies)
            if follow_redirects
            else build_opener(cookies, NoRedirect())
        )
        self._deadline = deadline

    def __call__(
        self, method: str, url: str, body: bytes | None
    ) -> PreviewHttpResponse:
        return self.request(method, url, body, {})

    def request(
        self, method: str, url: str, body: bytes | None, headers: Mapping[str, str]
    ) -> PreviewHttpResponse:
        return _urllib_http(
            method,
            url,
            body,
            opener=self._opener,
            headers=headers,
            timeout_seconds=_remaining(self._deadline)
            if self._deadline is not None
            else 30,
        )


def _urllib_http(
    method: str,
    url: str,
    body: bytes | None,
    *,
    opener: Any | None = None,
    headers: Mapping[str, str] | None = None,
    timeout_seconds: float = 30,
) -> PreviewHttpResponse:
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    request = Request(
        url,
        method=method,
        data=body,
        headers={
            **({"Content-Type": "application/json"} if body is not None else {}),
            **(headers or {}),
        },
    )
    try:
        active_opener = opener.open if opener is not None else urlopen
        with active_opener(request, timeout=timeout_seconds) as response:  # noqa: S310
            return PreviewHttpResponse(
                int(response.status), dict(response.headers.items()), response.read()
            )
    except HTTPError as error:
        return PreviewHttpResponse(
            int(error.code), dict(error.headers.items()), error.read()
        )


def _manifest_sha256(path: str) -> str:
    import hashlib
    from pathlib import Path

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _required_manifest_string(manifest: Mapping[str, object], name: str) -> str:
    value = manifest.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError("manifest field unavailable")
    return value


def _manifest_digests(manifest: Mapping[str, object]) -> dict[str, str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("manifest artifacts unavailable")
    digests: dict[str, str] = {}
    for name in ("web", "runtime"):
        artifact = artifacts.get(name)
        if not isinstance(artifact, Mapping):
            raise ValueError("manifest artifact unavailable")
        digest = artifact.get("digest")
        if not isinstance(digest, str):
            raise ValueError("manifest digest unavailable")
        digests[name] = digest
    return digests


if __name__ == "__main__":
    raise SystemExit(main())
