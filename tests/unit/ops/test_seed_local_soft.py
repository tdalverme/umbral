# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Seed local soft layer smoke tests (014-soft-preferences-chat, T006)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]


def _load_seed():
    path = ROOT / "scripts" / "seed-local.py"
    spec = importlib.util.spec_from_file_location("umbral_seed_local", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeCriteria:
    def __init__(self) -> None:
        self.seed_calls: list[UUID] = []
        self.extractions: list[tuple[str, str]] = []

    def seed_registry(self, correlation_id: UUID) -> int:
        self.seed_calls.append(correlation_id)
        return 0

    def process_extraction(self, scope, *, job_execution_id, correlation_id):
        self.extractions.append((scope.kind, scope.target))
        return {"published": 3, "failed": 2, "superseded": 0}


def test_seed_soft_sows_registry_and_extracts_full_scope() -> None:
    seed = _load_seed()
    criteria = _FakeCriteria()
    seed._seed_soft(None, criteria=criteria)  # type: ignore[attr-defined]
    assert len(criteria.seed_calls) == 1
    assert criteria.extractions == [("full", "full")]


def test_seed_soft_runs_twice_are_idempotent_at_service_level() -> None:
    seed = _load_seed()
    criteria = _FakeCriteria()
    seed._seed_soft(None, criteria=criteria)  # type: ignore[attr-defined]
    seed._seed_soft(None, criteria=criteria)  # type: ignore[attr-defined]
    assert len(criteria.seed_calls) == 2
    assert len(criteria.extractions) == 2
    assert criteria.extractions[0] == criteria.extractions[1]


def test_seed_builds_local_criteria_with_fake_extractor() -> None:
    seed = _load_seed()
    criteria = seed._build_local_criteria(None)  # type: ignore[attr-defined]
    assert criteria is not None
    assert criteria.extractor is not None
