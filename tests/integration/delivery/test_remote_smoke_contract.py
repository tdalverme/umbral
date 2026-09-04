from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

from umbral.ops.identity import main as identity_main
from umbral.ops.smoke import (
    BuiltInPreviewObserver,
    CookieHttpClient,
    ObservedPreviewMessage,
    PreviewHttpResponse,
    PreviewSmokeConfig,
    PreviewSmokeObserver,
    ResendPreviewObserver,
    _runtime_surfaces_match,
    run_preview_identity_smoke,
)


def test_scanner_client_observes_real_redirect_without_following_it() -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/capture":
                self.send_response(303)
                self.send_header("Location", "/confirm")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()

        def log_message(self, *_: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        browser = CookieHttpClient()
        scanner = CookieHttpClient(follow_redirects=False)
        assert browser("GET", f"{origin}/capture", None).status_code == 200
        response = scanner("GET", f"{origin}/capture", None)
        assert response.status_code == 303
        assert response.headers["Location"] == "/confirm"
    finally:
        server.shutdown()
        server.server_close()


class RecordingObserver(PreviewSmokeObserver):
    def __init__(self) -> None:
        self.preloaded = 0
        self.events: list[tuple[str, UUID]] = []

    def preload_invitation(self) -> str:
        self.preloaded += 1
        return "00000000-0000-0000-0000-000000000101"

    def runtime_surfaces(self, *, timeout_seconds: int) -> tuple[dict[str, str], ...]:
        assert timeout_seconds == 30
        rows = (
            {
                "surface": "web",
                "state": "ready",
                "release_id": "release-20260801",
                "manifest_sha256": "a" * 64,
                "artifact_digest": "sha256:" + "b" * 64,
                "correlation_id": "00000000-0000-0000-0000-000000000501",
            },
            {
                "surface": "api",
                "state": "ready",
                "release_id": "release-20260801",
                "manifest_sha256": "a" * 64,
                "artifact_digest": "sha256:" + "c" * 64,
                "correlation_id": "00000000-0000-0000-0000-000000000502",
            },
            {
                "surface": "worker",
                "state": "ready",
                "release_id": "release-20260801",
                "manifest_sha256": "a" * 64,
                "artifact_digest": "sha256:" + "c" * 64,
                "correlation_id": "00000000-0000-0000-0000-000000000503",
            },
            {
                "surface": "scheduler",
                "state": "ready",
                "release_id": "release-20260801",
                "manifest_sha256": "a" * 64,
                "artifact_digest": "sha256:" + "c" * 64,
                "correlation_id": "00000000-0000-0000-0000-000000000504",
            },
        )
        return tuple(
            row | {"observed_at": datetime.now(timezone.utc).isoformat()}
            for row in rows
        )

    def wait_for_magic_link(
        self,
        correlation_id: UUID,
        *,
        recipient: str,
        requested_at: datetime,
        timeout_seconds: int,
    ) -> ObservedPreviewMessage:
        assert timeout_seconds == 30
        assert recipient == "operator-private@example.test" or recipient.endswith(
            "@resend.dev"
        )
        assert requested_at == datetime(2026, 8, 1, tzinfo=timezone.utc)
        return ObservedPreviewMessage(
            message_id=f"email_{correlation_id.hex}",
            capture_url=(
                "https://preview.example.test/auth/capture?"
                "attempt_id=00000000-0000-0000-0000-000000000201&"
                "token_hash=private-provider-token-value-that-is-long-enough"
            ),
            correlation_id=correlation_id,
        )

    def trigger_delivery_event(self, scenario: str, correlation_id: UUID) -> str:
        self.events.append((scenario, correlation_id))
        return f"event_{scenario}"

    def prepare_delivery_recipient(self, scenario: str, correlation_id: UUID) -> str:
        self.events.append((scenario, correlation_id))
        return f"{scenario}+{correlation_id.hex[:16]}@resend.dev"

    def cleanup_delivery_recipient(self, recipient: str) -> None:
        assert recipient.endswith("@resend.dev")

    def audit_projection_observed(
        self, provider_event_id: str, *, timeout_seconds: int
    ) -> bool:
        return (
            provider_event_id.startswith(("event_", "email_")) and timeout_seconds == 30
        )

    def wait_for_no_magic_link(
        self,
        correlation_id: UUID,
        *,
        recipient: str,
        requested_at: datetime,
        timeout_seconds: int,
    ) -> bool:
        return (
            recipient.startswith("not-invited-")
            and requested_at == datetime(2026, 8, 1, tzinfo=timezone.utc)
            and timeout_seconds == 30
        )

    def backdate_session(self, user_id: UUID, *, timeout_seconds: int) -> bool:
        return (
            user_id == UUID("00000000-0000-0000-0000-000000000601")
            and timeout_seconds == 30
        )

    def evidence_text(self) -> str:
        return "only operational output"


def test_preview_smoke_uses_only_the_public_bff_and_returns_closed_evidence() -> None:
    """A direct API host or private provider material must not escape the process."""

    calls: list[tuple[str, str, bytes | None]] = []
    confirm_calls = 0
    session_calls = 0

    def http(method: str, url: str, body: bytes | None) -> PreviewHttpResponse:
        nonlocal confirm_calls, session_calls
        calls.append((method, url, body))
        assert url.startswith("https://preview.example.test/")
        path = url.removeprefix("https://preview.example.test")
        if path == "/health":
            return PreviewHttpResponse(200, {}, b'{"status":"alive"}')
        if path == "/ready":
            return PreviewHttpResponse(
                200,
                {},
                b'{"surface":"web","state":"ready","release_id":"release-20260801"}',
            )
        if path == "/version":
            return PreviewHttpResponse(
                200,
                {},
                b'{"surface":"web","release_id":"release-20260801",'
                b'"manifest_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
                b'"artifact_digest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}',
            )
        if path == "/api/auth/magic-link-requests":
            return PreviewHttpResponse(202, {}, b'{"message":"accepted"}')
        if path.startswith("/auth/capture"):
            return PreviewHttpResponse(
                303, {"set-cookie": "umbral_capture=sealed; Path=/auth"}, b""
            )
        if path == "/api/auth/confirmations":
            confirm_calls += 1
            if confirm_calls in {1, 3}:
                return PreviewHttpResponse(
                    204, {"set-cookie": "umbral_local_session=session; Path=/"}, b""
                )
            return PreviewHttpResponse(409, {}, b'{"code":"auth.magic_link_reused"}')
        if path == "/api/auth/session":
            session_calls += 1
            if session_calls in {2, 4}:
                return PreviewHttpResponse(401, {}, b'{"code":"auth.session_expired"}')
            return PreviewHttpResponse(
                200,
                {},
                b'{"user_id":"00000000-0000-0000-0000-000000000601","roles":["user"]}',
            )
        if path == "/api/auth/logout":
            return PreviewHttpResponse(204, {}, b"")
        raise AssertionError(path)

    observer = RecordingObserver()
    report = run_preview_identity_smoke(
        PreviewSmokeConfig(
            public_web_base_url="https://preview.example.test",
            release_id="release-20260801",
            manifest_sha256="a" * 64,
            artifact_digests={
                "web": "sha256:" + "b" * 64,
                "runtime": "sha256:" + "c" * 64,
            },
            invitation_id="00000000-0000-0000-0000-000000000101",
            invited_email="operator-private@example.test",
            resend_observation_token="re_private_observation_token",
            timeout_seconds=30,
        ),
        http=http,
        observer=observer,
        now=lambda: datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    assert report.passed, [
        check.scenario for check in report.checks if not check.passed
    ]
    assert observer.preloaded == 0
    assert [scenario for scenario, _ in observer.events] == [
        "delivered",
        "bounced",
        "complained",
    ]
    evidence = report.to_dict()
    checks = cast("list[dict[str, str]]", evidence["checks"])
    serialized = json.dumps(evidence, sort_keys=True)
    assert "operator-private@example.test" not in serialized
    assert "private-provider-token-value-that-is-long-enough" not in serialized
    assert "re_private_observation_token" not in serialized
    assert all("api.railway.internal" not in url for _, url, _ in calls)
    assert {check["scenario"] for check in checks} == {
        "runtime_identity",
        "invitation",
        "invited",
        "scanner_prefetch",
        "explicit_confirmation",
        "single_use",
        "repeat",
        "non_invited",
        "authorization",
        "logout",
        "idle_expiry",
        "delivered",
        "bounced",
        "complained",
        "redaction",
    }


def test_preload_invitation_reads_secret_values_only_by_environment_variable_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An operator command must not take secret values as argv values."""

    seen: dict[str, str] = {}

    def preload(email: str, database_url: str) -> str:
        seen["email"] = email
        seen["database_url"] = database_url
        return "00000000-0000-0000-0000-000000000301"

    result = identity_main(
        [
            "preload-invitation",
            "--email-env",
            "UMBRAL_SMOKE_INVITEE",
            "--database-url-env",
            "UMBRAL_OPERATOR_DATABASE_URL",
        ],
        environ={
            "UMBRAL_SMOKE_INVITEE": "private-invite@example.test",
            "UMBRAL_OPERATOR_DATABASE_URL": "postgresql://private:private@operator.example.test/umbral",
        },
        preload_invitation=preload,
    )

    assert result == 0
    assert seen == {
        "email": "private-invite@example.test",
        "database_url": "postgresql://private:private@operator.example.test/umbral",
    }
    assert capsys.readouterr().out.strip() == (
        '{"invitation_id":"00000000-0000-0000-0000-000000000301","result":"accepted"}'
    )


def test_resend_observer_lists_then_loads_a_message_without_exposing_credentials() -> (
    None
):
    """The Resend observer obtains capture material at its injected API boundary."""

    observed_urls: list[str] = []

    def resend_get(url: str, token: str) -> object:
        observed_urls.append(url)
        assert token == "re_private_observation_token"
        if url.endswith("/emails"):
            return {
                "data": [
                    {
                        "id": "email_01HZY6A2D5YQ3DAN9F5C4XE5QY",
                        "to": "operator-private@example.test",
                        "created_at": "2026-08-01T00:00:00Z",
                        "tags": [
                            {
                                "name": "correlation_id",
                                "value": "00000000-0000-0000-0000-000000000403",
                            }
                        ],
                    }
                ]
            }
        return {
            "id": "email_01HZY6A2D5YQ3DAN9F5C4XE5QY",
            "html": (
                '<a href="https://preview.example.test/auth/capture?'
                "attempt_id=00000000-0000-0000-0000-000000000401&"
                'token_hash=private-provider-token-value-that-is-long-enough">Ingresar</a>'
            ),
            "text": "",
        }

    observer = ResendPreviewObserver(
        observation_token="re_private_observation_token",
        resend_get=resend_get,
        preload=lambda: "00000000-0000-0000-0000-000000000402",
        event_trigger=lambda _, __: "event_01HZY6A2D5YQ3DAN9F5C4XE5QY",
        audit_projection=lambda _, timeout_seconds: timeout_seconds == 30,
    )
    correlation_id = UUID("00000000-0000-0000-0000-000000000403")

    message = observer.wait_for_magic_link(
        correlation_id,
        recipient="operator-private@example.test",
        requested_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        timeout_seconds=30,
    )

    assert message.message_id == "email_01HZY6A2D5YQ3DAN9F5C4XE5QY"
    assert message.correlation_id == correlation_id
    assert observed_urls == [
        "https://api.resend.com/emails",
        "https://api.resend.com/emails/email_01HZY6A2D5YQ3DAN9F5C4XE5QY",
    ]


def test_preview_smoke_redacts_nested_observer_evidence() -> None:
    from umbral.ops.smoke import _redaction_clean

    assert not _redaction_clean(
        {"errors": [{"context": {"token": "canary-secret"}}]}, "canary-secret"
    )


def test_runtime_surfaces_accept_exactly_four_fresh_matching_rows() -> None:
    assert _runtime_surfaces_match(_smoke_config(), _SurfaceObserver(_surface_rows()))


def test_builtin_runtime_surfaces_retries_until_all_surfaces_are_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _surface_rows()
    not_ready = [dict(row) for row in rows]
    not_ready[1]["state"] = "not_ready"
    snapshots = [not_ready, rows]
    queries: list[str] = []
    fields = (
        "surface",
        "state",
        "release_id",
        "manifest_sha256",
        "artifact_digest",
        "correlation_id",
        "observed_at",
    )

    class Connection:
        def __init__(self, snapshot: list[dict[str, str]]) -> None:
            self.snapshot = snapshot

        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def cursor(self) -> "Connection":
            return self

        def execute(self, query: str) -> None:
            queries.append(query)

        def fetchall(self) -> list[tuple[object, ...]]:
            return [
                tuple(
                    datetime.fromisoformat(row[field])
                    if field == "observed_at"
                    else row[field]
                    for field in fields
                )
                for row in self.snapshot
            ]

    connection_index = 0

    def connect(*_args: object, **_kwargs: object) -> Connection:
        nonlocal connection_index
        snapshot = snapshots[min(connection_index, len(snapshots) - 1)]
        connection_index += 1
        return Connection(snapshot)

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect))

    from umbral.ops import smoke as smoke_module

    monkeypatch.setattr(smoke_module, "_sleep_remaining", lambda _deadline: None)

    observer = BuiltInPreviewObserver(
        database_url="postgresql://preview.example.test/db",
        observation_token="",
        sender="sender@example.test",
    )

    assert observer.runtime_surfaces(timeout_seconds=1)[1]["state"] == "ready"
    assert len(queries) == 2


def test_builtin_runtime_surfaces_returns_last_snapshot_when_deadline_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _surface_rows()
    rows[0] = {**rows[0], "state": "starting"}
    fields = (
        "surface",
        "state",
        "release_id",
        "manifest_sha256",
        "artifact_digest",
        "correlation_id",
        "observed_at",
    )

    class Connection:
        def __enter__(self) -> "Connection":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def cursor(self) -> "Connection":
            return self

        def execute(self, _query: str) -> None:
            return None

        def fetchall(self) -> list[tuple[object, ...]]:
            return [
                tuple(
                    datetime.fromisoformat(row[field])
                    if field == "observed_at"
                    else row[field]
                    for field in fields
                )
                for row in rows
            ]

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=lambda *_args, **_kwargs: Connection()))

    from umbral.ops import smoke as smoke_module

    remaining_calls = 0

    def remaining(_deadline: float) -> float:
        nonlocal remaining_calls
        remaining_calls += 1
        if remaining_calls > 1:
            raise TimeoutError("preview smoke timed out")
        return 1.0

    monkeypatch.setattr(smoke_module, "_remaining", remaining)
    monkeypatch.setattr(smoke_module, "_sleep_remaining", lambda _deadline: None)

    observer = BuiltInPreviewObserver(
        database_url="postgresql://preview.example.test/db",
        observation_token="",
        sender="sender@example.test",
    )

    observed = observer.runtime_surfaces(timeout_seconds=1)

    assert len(observed) == len(rows)
    assert {row["surface"] for row in observed} == {
        "web",
        "api",
        "worker",
        "scheduler",
    }


def test_preview_smoke_does_not_start_identity_flow_after_runtime_failure() -> None:
    class NotReadyObserver(RecordingObserver):
        def runtime_surfaces(self, *, timeout_seconds: int) -> tuple[dict[str, str], ...]:
            raise TimeoutError("preview smoke timed out")

    calls: list[str] = []

    def http(method: str, url: str, body: bytes | None) -> PreviewHttpResponse:
        del body
        path = url.removeprefix("https://preview.example.test")
        calls.append(f"{method} {path}")
        if path == "/health":
            return PreviewHttpResponse(200, {}, b'{"status":"alive"}')
        if path == "/ready":
            return PreviewHttpResponse(
                200,
                {},
                b'{"surface":"web","state":"ready","release_id":"release-20260801"}',
            )
        if path == "/version":
            return PreviewHttpResponse(
                200,
                {},
                b'{"surface":"web","release_id":"release-20260801",'
                b'"manifest_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",'
                b'"artifact_digest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}',
            )
        raise AssertionError(path)

    report = run_preview_identity_smoke(
        _smoke_config(),
        http=http,
        observer=NotReadyObserver(),
        now=lambda: datetime(2026, 8, 1, tzinfo=timezone.utc),
    )

    assert len(report.checks) == 15
    assert report.checks[0].scenario == "runtime_identity"
    assert report.checks[0].code == "smoke.failed"
    assert "POST /api/auth/magic-link-requests" not in calls


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows.__setitem__(
            0,
            {
                **rows[0],
                "observed_at": (
                    datetime.now(timezone.utc) - timedelta(minutes=11)
                ).isoformat(),
            },
        ),
        lambda rows: rows.pop(),
        lambda rows: rows.__setitem__(3, {**rows[3], "surface": "worker"}),
        lambda rows: rows.__setitem__(
            0, {**rows[0], "artifact_digest": "sha256:" + "d" * 64}
        ),
        lambda rows: rows.__setitem__(0, {**rows[0], "release_id": "wrong-release"}),
        lambda rows: rows.__setitem__(0, {**rows[0], "manifest_sha256": "d" * 64}),
        lambda rows: rows.__setitem__(0, {**rows[0], "state": "degraded"}),
    ],
)
def test_runtime_surfaces_fail_closed_for_invalid_identity_or_freshness(
    mutate: Callable[[list[dict[str, str]]], None],
) -> None:
    rows = _surface_rows()
    mutate(rows)
    assert not _runtime_surfaces_match(_smoke_config(), _SurfaceObserver(rows))


class _SurfaceObserver(PreviewSmokeObserver):
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def runtime_surfaces(self, *, timeout_seconds: int) -> tuple[dict[str, str], ...]:
        assert timeout_seconds == 30
        return tuple(self.rows)


def _smoke_config() -> PreviewSmokeConfig:
    return PreviewSmokeConfig(
        public_web_base_url="https://preview.example.test",
        release_id="release-20260801",
        manifest_sha256="a" * 64,
        artifact_digests={"web": "sha256:" + "b" * 64, "runtime": "sha256:" + "c" * 64},
        invitation_id="00000000-0000-0000-0000-000000000101",
        invited_email="operator-private@example.test",
        resend_observation_token="token",
        timeout_seconds=30,
    )


def _surface_rows() -> list[dict[str, str]]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "surface": surface,
            "state": "ready",
            "release_id": "release-20260801",
            "manifest_sha256": "a" * 64,
            "artifact_digest": "sha256:" + ("b" if surface == "web" else "c") * 64,
            "correlation_id": f"00000000-0000-0000-0000-00000000050{index}",
            "observed_at": now,
        }
        for index, surface in enumerate(("web", "api", "worker", "scheduler"), start=1)
    ]
