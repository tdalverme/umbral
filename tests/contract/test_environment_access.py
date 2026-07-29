"""Environment access policy contracts (T085)."""

from __future__ import annotations

import pytest

from umbral.ops.access import AccessPolicy, AccessPolicyViolation


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
