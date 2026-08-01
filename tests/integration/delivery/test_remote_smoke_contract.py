from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from umbral.ops.identity import main as identity_main
from umbral.ops.smoke import (
    ObservedPreviewMessage,
    PreviewHttpResponse,
    PreviewSmokeConfig,
    PreviewSmokeObserver,
    ResendPreviewObserver,
    run_preview_identity_smoke,
)


class RecordingObserver(PreviewSmokeObserver):
    def __init__(self) -> None:
        self.preloaded = 0
        self.events: list[tuple[str, UUID]] = []

    def preload_invitation(self) -> str:
        self.preloaded += 1
        return "00000000-0000-0000-0000-000000000101"

    def wait_for_magic_link(
        self, correlation_id: UUID, *, timeout_seconds: int
    ) -> ObservedPreviewMessage:
        assert timeout_seconds == 30
        return ObservedPreviewMessage(
            message_id="email_01HZY6A2D5YQ3DAN9F5C4XE5QY",
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

    def audit_projection_observed(
        self, provider_event_id: str, *, timeout_seconds: int
    ) -> bool:
        return provider_event_id.startswith("event_") and timeout_seconds == 30

    def evidence_text(self) -> str:
        return "only operational output"


def test_preview_smoke_uses_only_the_public_bff_and_returns_closed_evidence() -> None:
    """A direct API host or private provider material must not escape the process."""

    calls: list[tuple[str, str, bytes | None]] = []
    confirm_calls = 0

    def http(method: str, url: str, body: bytes | None) -> PreviewHttpResponse:
        nonlocal confirm_calls
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
            if confirm_calls == 1:
                return PreviewHttpResponse(
                    204, {"set-cookie": "umbral_local_session=session; Path=/"}, b""
                )
            return PreviewHttpResponse(409, {}, b'{"code":"auth.magic_link_reused"}')
        if path == "/api/auth/session":
            return PreviewHttpResponse(200, {}, b'{"roles":["user"]}')
        if path == "/api/auth/logout":
            return PreviewHttpResponse(204, {}, b"")
        if path == "/api/auth/session?idle=boundary":
            return PreviewHttpResponse(401, {}, b'{"code":"auth.session_expired"}')
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
    assert observer.preloaded == 1
    assert [scenario for scenario, _ in observer.events] == [
        "delivered",
        "bounced",
        "complained",
    ]
    evidence = report.to_dict()
    serialized = json.dumps(evidence, sort_keys=True)
    assert "operator-private@example.test" not in serialized
    assert "private-provider-token-value-that-is-long-enough" not in serialized
    assert "re_private_observation_token" not in serialized
    assert all("api.railway.internal" not in url for _, url, _ in calls)
    assert {check["scenario"] for check in evidence["checks"]} == {
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
    capsys,
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


def test_resend_observer_lists_then_loads_a_message_without_exposing_credentials(
) -> None:
    """The Resend observer obtains capture material at its injected API boundary."""

    observed_urls: list[str] = []

    def resend_get(url: str, token: str) -> object:
        observed_urls.append(url)
        assert token == "re_private_observation_token"
        if url.endswith("/emails"):
            return {"data": [{"id": "email_01HZY6A2D5YQ3DAN9F5C4XE5QY"}]}
        return {
            "id": "email_01HZY6A2D5YQ3DAN9F5C4XE5QY",
            "html": (
                '<a href="https://preview.example.test/auth/capture?'
                'attempt_id=00000000-0000-0000-0000-000000000401&'
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

    message = observer.wait_for_magic_link(correlation_id, timeout_seconds=30)

    assert message.message_id == "email_01HZY6A2D5YQ3DAN9F5C4XE5QY"
    assert message.correlation_id == correlation_id
    assert observed_urls == [
        "https://api.resend.com/emails",
        "https://api.resend.com/emails/email_01HZY6A2D5YQ3DAN9F5C4XE5QY",
    ]
