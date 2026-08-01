"""Environment access policy contracts (T085)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from umbral.infrastructure.config.settings import Settings
from umbral.ops.access import AccessPolicy, AccessPolicyViolation


def test_beta_web_access_contract_keeps_api_private() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-File",
            str(repo_root / "scripts" / "deploy" / "verify-access.ps1"),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "policy": "infra\\cloudflare\\access-policy.json",
        "access_mode": "product_session",
        "web_public_domain": True,
        "api_public_domain": False,
        "datastores_private_or_managed": True,
        "umbral_session_protection": True,
        "public_paths": [
            "/health",
            "/login",
            "/auth/capture",
            "/auth/confirm",
            "/api/auth/magic-link-requests",
            "/api/webhooks/email",
        ],
        "credentials_observed": False,
    }


def test_only_health_is_public_and_origins_are_closed() -> None:
    policy = AccessPolicy.default()

    assert policy.is_public_path("/health")
    assert not policy.is_public_path("/ready")
    assert not policy.is_public_path("/api/v1/search")
    assert policy.allowed_origins == ()
    assert policy.require_access_header


@pytest.mark.parametrize(
    "path",
    ["health", "/health/", "/health?debug=true", "/api/v1?token=secret"],
)
def test_policy_rejects_ambiguous_or_sensitive_bypass_paths(path: str) -> None:
    policy = AccessPolicy.default()

    with pytest.raises(AccessPolicyViolation):
        policy.assert_allowed_public_path(path)


def test_jwt_claims_must_match_audience_and_expiry() -> None:
    policy = AccessPolicy.default()

    policy.validate_claims(
        {"aud": "umbral-runtime", "exp": 2_000_000_000}, now=1_900_000_000
    )

    with pytest.raises(AccessPolicyViolation):
        policy.validate_claims(
            {"aud": "other", "exp": 2_000_000_000}, now=1_900_000_000
        )
    with pytest.raises(AccessPolicyViolation):
        policy.validate_claims(
            {"aud": "umbral-runtime", "exp": 1_800_000_000}, now=1_900_000_000
        )


def test_preview_product_session_mode_does_not_require_cloudflare_audience() -> None:
    settings = Settings.from_environment(
        {
            "UMBRAL_ENV": "preview",
            "UMBRAL_RELEASE_ID": "preview-test",
            "UMBRAL_RELEASE_MANIFEST": "/run/secrets/release.json",
            "UMBRAL_RELEASE_DIGEST": "sha256:" + "a" * 64,
            "DATABASE_URL": "postgresql://user:pass@db.preview.invalid/app",
            "REDIS_URL": "redis://redis.railway.internal/0",
            "OBJECT_STORE_BACKEND": "s3",
            "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.preview.invalid",
            "SENTRY_DSN": "https://sentry.invalid/1",
            "UMBRAL_API_BASE_URL": "http://api.railway.internal:8000",
            "UMBRAL_ACCESS_MODE": "product_session",
            "IDENTITY_PROVIDER": "supabase",
            "SUPABASE_URL": "https://bpwgyvetbneghrtxcadm.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test_value",
            "IDENTITY_ISSUER": "https://bpwgyvetbneghrtxcadm.supabase.co/auth/v1",
            "IDENTITY_CAPTURE_ORIGIN": "https://preview.umbral.invalid",
            "EMAIL_PROVIDER": "resend",
            "RESEND_API_KEY": "re_test_value",
            "RESEND_FROM_EMAIL": "Umbral <onboarding@resend.dev>",
            "EMAIL_WEBHOOK_SECRET": "whsec_test_value",
        }
    )

    assert settings.access_mode == "product_session"
