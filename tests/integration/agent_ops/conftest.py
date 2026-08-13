# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Shared Postgres backend for agent ops integration tests."""

from __future__ import annotations

from tests.integration.agent.conftest import (  # noqa: F401
    agent_backend,
)
