"""API composition configuration behavior."""

from __future__ import annotations

import pytest

from umbral.api.dependencies import build_runtime_dependencies
from umbral.infrastructure.config.settings import SettingsValidationError


def test_runtime_dependencies_reject_unknown_runtime_environment_settings() -> None:
    with pytest.raises(SettingsValidationError) as raised:
        build_runtime_dependencies({"UMBRAL_UNDECLARED_OPTION": "enabled"})

    assert raised.value.rule_code == "CONFIG_UNKNOWN_SETTING"
    assert raised.value.field_name == "UMBRAL_UNDECLARED_OPTION"
