from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest

from umbral.application.identity.contracts import IdentityError
from umbral.infrastructure.identity.supabase import SupabaseIdentityAdapter


def _access_token(*, issuer: str, subject: str) -> str:
    payload = json.dumps({"iss": issuer, "sub": subject}).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    return f"header.{encoded}.signature"


class FakeSupabaseClient:
    def __init__(self, *, response: object) -> None:
        self.generate_requests: list[dict[str, object]] = []
        self.verify_requests: list[dict[str, object]] = []
        self.sign_out_requests: list[tuple[str, str]] = []
        self._response = response
        self.auth = SimpleNamespace(
            admin=SimpleNamespace(
                generate_link=self.generate_link,
                sign_out=self.sign_out,
            ),
            verify_otp=self.verify_otp,
        )

    def generate_link(self, params: dict[str, object]) -> object:
        self.generate_requests.append(params)
        return self._response

    def verify_otp(self, params: dict[str, object]) -> object:
        self.verify_requests.append(params)
        return self._response

    def sign_out(self, jwt: str, scope: str = "global") -> None:
        self.sign_out_requests.append((jwt, scope))


def test_adapter_generates_capture_url_from_only_supabase_hashed_token() -> None:
    now = datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc)
    attempt_id = uuid4()
    client = FakeSupabaseClient(
        response=SimpleNamespace(
            properties=SimpleNamespace(
                hashed_token="only+this/token=hash",
                action_link="https://untrusted.invalid/?token=must-not-leak",
            )
        )
    )
    adapter = SupabaseIdentityAdapter(
        issuer="https://project.supabase.co/auth/v1",
        capture_origin="https://preview.umbral.invalid/",
        client=client,
    )

    generated = adapter.generate_magic_link(
        attempt_id=attempt_id,
        email="  PERSON@Example.COM  ",
        now=now,
    )

    assert client.generate_requests == [
        {
            "type": "magiclink",
            "email": "person@example.com",
            "options": {"redirect_to": "https://preview.umbral.invalid/auth/capture"},
        }
    ]
    query = parse_qs(urlparse(generated.capture_url).query)
    assert urlparse(generated.capture_url).path == "/auth/capture"
    assert query == {
        "attempt_id": [str(attempt_id)],
        "token_hash": ["only+this/token=hash"],
    }
    assert generated.expires_at == now + timedelta(minutes=15)


def test_adapter_verifies_magic_link_and_maps_only_provider_neutral_proof() -> None:
    now = datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc)
    issuer = "https://project.supabase.co/auth/v1"
    subject = "provider-user-id"
    access_token = _access_token(issuer=issuer, subject=subject)
    client = FakeSupabaseClient(
        response=SimpleNamespace(
            user=SimpleNamespace(
                id=subject,
                email="person@example.com",
                email_confirmed_at="2026-08-01T12:00:00Z",
            ),
            session=SimpleNamespace(access_token=access_token),
        )
    )
    adapter = SupabaseIdentityAdapter(
        issuer=issuer,
        capture_origin="https://preview.umbral.invalid",
        client=client,
    )

    proof = adapter.verify_magic_link(
        attempt_id=uuid4(), token_hash="provider-token-hash", now=now
    )

    assert client.verify_requests == [
        {
            "type": "magiclink",
            "token_hash": "provider-token-hash",
            "options": {"shouldCreateUser": True},
        }
    ]
    assert proof.provider == "supabase"
    assert proof.issuer == issuer
    assert proof.subject == subject
    assert proof.verified_email == "person@example.com"
    assert proof.verified_at == now
    assert proof.revocation_handle == access_token


def test_adapter_revokes_the_transient_provider_session_globally() -> None:
    client = FakeSupabaseClient(response=SimpleNamespace())
    adapter = SupabaseIdentityAdapter(
        issuer="https://project.supabase.co/auth/v1",
        capture_origin="https://preview.umbral.invalid",
        client=client,
    )

    adapter.revoke_provider_session("provider-access-token")

    assert client.sign_out_requests == [("provider-access-token", "global")]


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(user=None, session=None),
        SimpleNamespace(
            user=SimpleNamespace(id="subject", email=None, email_confirmed_at="now"),
            session=SimpleNamespace(
                access_token=_access_token(
                    issuer="https://project.supabase.co/auth/v1", subject="subject"
                )
            ),
        ),
        SimpleNamespace(
            user=SimpleNamespace(
                id="subject", email="person@example.com", email_confirmed_at="now"
            ),
            session=SimpleNamespace(access_token=None),
        ),
        SimpleNamespace(
            user=SimpleNamespace(
                id="subject", email="person@example.com", email_confirmed_at="now"
            ),
            session=SimpleNamespace(
                access_token=_access_token(
                    issuer="https://other.supabase.co/auth/v1", subject="subject"
                )
            ),
        ),
    ],
)
def test_adapter_rejects_invalid_provider_proofs(response: object) -> None:
    client = FakeSupabaseClient(response=response)
    adapter = SupabaseIdentityAdapter(
        issuer="https://project.supabase.co/auth/v1",
        capture_origin="https://preview.umbral.invalid",
        client=client,
    )

    with pytest.raises(IdentityError) as error:
        adapter.verify_magic_link(
            attempt_id=uuid4(),
            token_hash="provider-token-hash",
            now=datetime.now(timezone.utc),
        )

    assert error.value.code == "auth.link_unavailable"


def test_adapter_fails_closed_when_sdk_call_or_global_sign_out_fails() -> None:
    class FailingClient(FakeSupabaseClient):
        def generate_link(self, params: dict[str, object]) -> object:
            raise RuntimeError("provider unavailable")

        def sign_out(self, jwt: str, scope: str = "global") -> None:
            raise RuntimeError("provider unavailable")

    adapter = SupabaseIdentityAdapter(
        issuer="https://project.supabase.co/auth/v1",
        capture_origin="https://preview.umbral.invalid",
        client=FailingClient(response=SimpleNamespace()),
    )

    with pytest.raises(IdentityError) as generation_error:
        adapter.generate_magic_link(
            attempt_id=uuid4(),
            email="person@example.com",
            now=datetime.now(timezone.utc),
        )
    with pytest.raises(IdentityError) as sign_out_error:
        adapter.revoke_provider_session("access-token")

    assert generation_error.value.code == "auth.provider_unavailable"
    assert sign_out_error.value.code == "auth.provider_unavailable"
