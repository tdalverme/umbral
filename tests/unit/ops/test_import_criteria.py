"""US: the criteria ops CLI seeds the concept registry idempotently.

The operator runs ``python -m umbral.ops.criteria seed`` against the target
environment; the registry insertion is delegated to the real criteria service
(its idempotency is covered by the service tests), so here the composition
boundary is mocked.
"""

from __future__ import annotations

from typing import Any
from unittest import mock
from uuid import UUID

import pytest

from umbral.ops.criteria import main


class _FakeCriteriaService:
    def __init__(self) -> None:
        self.seed_correlations: list[UUID] = []

    def seed_registry(self, *, correlation_id: UUID) -> int:
        self.seed_correlations.append(correlation_id)
        return len(self.seed_correlations) - 1


class _FakeDependencies:
    class _SessionProvider:
        session_factory: Any = object()

    session_provider = _SessionProvider()


def _run_seed(service: _FakeCriteriaService) -> int:
    with (
        mock.patch(
            "umbral.ops.criteria.build_process_dependencies",
            return_value=_FakeDependencies(),
        ),
        mock.patch(
            "umbral.ops.criteria.build_criteria_service",
            return_value=service,
        ),
    ):
        return main(["seed"])


def test_seed_command_registers_published_concepts() -> None:
    service = _FakeCriteriaService()

    assert _run_seed(service) == 0
    assert len(service.seed_correlations) == 1
    assert isinstance(service.seed_correlations[0], UUID)


def test_seed_command_is_idempotent_across_runs(capsys: Any) -> None:
    service = _FakeCriteriaService()

    _run_seed(service)
    first = capsys.readouterr().out.strip()
    _run_seed(service)
    second = capsys.readouterr().out.strip()

    assert first == "registered=0"
    assert second == "registered=1"
    # the service is called once per run with an independent correlation id
    assert len(service.seed_correlations) == 2
    assert service.seed_correlations[0] != service.seed_correlations[1]


def test_missing_or_unknown_subcommand_is_rejected() -> None:
    with pytest.raises(SystemExit):
        main([])
    with pytest.raises(SystemExit):
        main(["nope"])
