"""Behavioral contract for the environment-specific runtime settings boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict, cast

import pytest

from umbral.infrastructure.config.settings import Settings, SettingsValidationError


class ExpectedOutcome(TypedDict):
    accepted: bool
    rule_code: str


class ConfigurationCase(TypedDict):
    id: str
    environment: str
    input: dict[str, str]
    overrides: dict[str, str]
    expected: ExpectedOutcome


ROOT = Path(__file__).resolve().parents[3]
CONFIGURATION_CASES = ROOT / "tests" / "fixtures" / "configuration_cases.json"


def _load_cases() -> list[ConfigurationCase]:
    raw = json.loads(CONFIGURATION_CASES.read_text(encoding="utf-8"))
    return cast(list[ConfigurationCase], raw["cases"])


CASES = _load_cases()
ACCEPTED_CASES = [case for case in CASES if case["expected"]["accepted"]]
REJECTED_CASES = [case for case in CASES if not case["expected"]["accepted"]]


def _case_environment(case: ConfigurationCase) -> dict[str, str]:
    return {**case["input"], **case["overrides"]}


def _secret_canaries(case: ConfigurationCase) -> set[str]:
    sensitive_keys = {
        "DATABASE_URL",
        "REDIS_URL",
        "SENTRY_DSN",
        "SUPABASE_SECRET_KEY",
        "UMBRAL_ACCESS_AUDIENCE",
        "RESEND_API_KEY",
        "EMAIL_WEBHOOK_SECRET",
    }
    return {
        value
        for key, value in _case_environment(case).items()
        if key in sensitive_keys and value
    }


@pytest.mark.parametrize("case", ACCEPTED_CASES, ids=lambda case: case["id"])
def test_settings_accepts_each_valid_environment_case(case: ConfigurationCase) -> None:
    settings = Settings.from_environment(_case_environment(case))

    assert settings.environment == case["environment"]
    assert settings.release_id == case["input"]["UMBRAL_RELEASE_ID"]


@pytest.mark.parametrize("case", REJECTED_CASES, ids=lambda case: case["id"])
def test_settings_rejects_each_invalid_environment_case_without_secret_diagnostics(
    case: ConfigurationCase,
) -> None:
    with pytest.raises(SettingsValidationError) as raised:
        Settings.from_environment(_case_environment(case))

    error = raised.value
    diagnostic = f"{error!s}\n{error!r}"
    assert error.rule_code == case["expected"]["rule_code"]
    assert error.field_name
    assert error.field_name in diagnostic
    assert error.rule_code in diagnostic
    assert not any(canary in diagnostic for canary in _secret_canaries(case))


def test_configuration_fixture_covers_required_invalid_setting_categories() -> None:
    expected_rule_codes = {
        "CONFIG_REQUIRED",
        "CONFIG_FORMAT",
        "CONFIG_EXAMPLE_VALUE",
        "CONFIG_PRIVATE_ENDPOINT",
        "CONFIG_BACKEND",
        "CONFIG_TLS_REQUIRED",
        "CONFIG_PRIVATE_INGRESS",
        "CONFIG_PROVIDER",
        "CONFIG_RELEASE_DIGEST_REQUIRED",
        "CONFIG_UNKNOWN_SETTING",
    }

    assert expected_rule_codes <= {
        case["expected"]["rule_code"] for case in REJECTED_CASES
    }
