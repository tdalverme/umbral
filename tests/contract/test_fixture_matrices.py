"""Contract checks for the finite foundation-runtime fixture matrices."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def _load_json(path: Path) -> Any:
    assert path.is_file(), f"missing fixture: {path.relative_to(ROOT)}"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _walk_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _walk_strings(child)]
    return []


def _assert_no_real_secret_markers(value: Any) -> None:
    serialized = "\n".join(_walk_strings(value))
    assert not re.search(r"AKIA[0-9A-Z]{16}", serialized)
    assert "sk_live_" not in serialized
    assert "-----BEGIN PRIVATE KEY-----" not in serialized
    assert "-----BEGIN OPENSSH PRIVATE KEY-----" not in serialized
    assert "password=" not in serialized


def test_configuration_matrix_is_finite_and_covers_required_rules() -> None:
    matrix = _load_json(FIXTURES / "configuration_cases.json")

    assert matrix["schema_version"] == 1
    cases = matrix["cases"]
    assert isinstance(cases, list)
    assert 3 <= len(cases) <= 32
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["environment"] for case in cases} == {"local", "preview", "production"}

    required_ids = {
        "local-valid",
        "preview-valid",
        "production-valid",
        "preview-missing-required",
        "preview-malformed-url",
        "preview-example-credential",
        "preview-localhost-backend",
        "production-filesystem-backend",
        "preview-plaintext-external-url",
        "production-public-ingress",
        "production-missing-release-digest",
        "production-unknown-setting",
    }
    assert required_ids <= {case["id"] for case in cases}

    for case in cases:
        assert set(case) == {"id", "environment", "input", "overrides", "expected"}
        assert isinstance(case["input"], dict)
        assert isinstance(case["overrides"], dict)
        assert set(case["expected"]) == {"accepted", "rule_code"}
        assert isinstance(case["expected"]["accepted"], bool)
        assert re.fullmatch(r"CONFIG_[A-Z0-9_]+", case["expected"]["rule_code"])

    accepted = {case["id"] for case in cases if case["expected"]["accepted"]}
    assert {"local-valid", "preview-valid", "production-valid"} <= accepted
    _assert_no_real_secret_markers(matrix)


def test_release_manifests_are_finite_deterministic_schema_inputs() -> None:
    manifest_dir = FIXTURES / "release-manifests"
    paths = sorted(manifest_dir.glob("*.json"))
    expected_variants = {
        "valid",
        "invalid-digest",
        "invalid-platform",
        "invalid-extra-property",
        "invalid-missing-required",
    }
    assert {path.stem for path in paths} == expected_variants

    manifests = {path.stem: _load_json(path) for path in paths}
    valid = manifests["valid"]
    assert set(valid) == {
        "schema_version",
        "release_id",
        "git_sha",
        "built_at",
        "contract_major",
        "database_revision",
        "config_schema_version",
        "artifacts",
    }
    assert valid["schema_version"] == 1
    assert valid["contract_major"] == 1
    assert re.fullmatch(r"[0-9a-f]{40}", valid["git_sha"])
    assert valid["built_at"] == "2026-01-01T00:00:00Z"
    assert set(valid["artifacts"]) == {"web", "runtime"}
    for artifact in valid["artifacts"].values():
        assert set(artifact) == {"image", "digest", "platform"}
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", artifact["digest"])
        assert artifact["platform"] == "linux/amd64"

    invalid_digest = manifests["invalid-digest"]["artifacts"]["web"]["digest"]
    assert not re.fullmatch(r"sha256:[0-9a-f]{64}", invalid_digest)
    invalid_platform = manifests["invalid-platform"]["artifacts"]["runtime"]["platform"]
    assert invalid_platform != "linux/amd64"
    assert "unexpected" in manifests["invalid-extra-property"]
    assert "git_sha" not in manifests["invalid-missing-required"]
    _assert_no_real_secret_markers(manifests)


def test_telemetry_canaries_are_finite_and_cover_sensitive_surfaces() -> None:
    matrix = _load_json(FIXTURES / "telemetry_canaries.json")

    allowed_fields = {
        "correlation_id",
        "request_id",
        "service_name",
        "environment",
        "release_id",
        "operation",
        "state",
        "status_code",
        "duration_ms",
        "route_template",
        "http_method",
        "error_code",
        "job_type",
        "job_state",
        "attempt_number",
        "queue_lag_ms",
        "object_operation",
        "content_class",
    }
    assert matrix["schema_version"] == 1
    assert set(matrix["allowed_metadata_fields"]) == allowed_fields
    assert matrix["expected_redaction_rule"] == "drop_unknown_and_sensitive_recursively"

    canaries = matrix["canaries"]
    assert isinstance(canaries, list)
    assert 8 <= len(canaries) <= 24
    assert len({canary["id"] for canary in canaries}) == len(canaries)
    required_categories = {
        "body",
        "query_path",
        "headers_cookies",
        "job_error",
        "object_error",
        "database_error",
        "release_failure",
        "access_failure",
    }
    assert required_categories <= {canary["category"] for canary in canaries}
    for canary in canaries:
        assert set(canary) == {"id", "category", "input", "expected"}
        assert isinstance(canary["input"], dict)
        assert canary["expected"]["redaction_rule"] == matrix["expected_redaction_rule"]
        assert canary["expected"]["retained_metadata"]
        assert canary["expected"]["redacted_paths"]

    serialized = "\n".join(_walk_strings(matrix))
    assert "canary" in serialized.lower()
    assert ".invalid" in serialized
    assert "203.0.113." in serialized
    _assert_no_real_secret_markers(matrix)


@pytest.mark.parametrize(
    "fixture_name", ["configuration_cases.json", "telemetry_canaries.json"]
)
def test_fixture_json_is_not_generated_or_unbounded(fixture_name: str) -> None:
    path = FIXTURES / fixture_name
    raw = path.read_text(encoding="utf-8")
    assert "random" not in raw.lower()
    assert "uuid4" not in raw.lower()
    assert "secrets.token" not in raw.lower()
    assert len(raw.splitlines()) <= 400
