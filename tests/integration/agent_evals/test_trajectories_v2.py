# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
"""Trajectory v2 suite over the real v4 copilot stack + Postgres.

Executes the published trajectory dataset through PostgresTrajectoryExecutor
(topology v4 with the real RadarService/PreferenceService/proposals) and
applies the strict gate: 100% critical invariants, >=95% trajectory success,
>=90% per family and zero wrong-target mutations.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tests.integration.agent.conftest import (  # noqa: F401
    agent_backend,
)
from tests.integration.radar.conftest import seed_user
from tests.support.containers import ServiceConnection

from umbral.application.agent_evals.trajectories.contracts import (
    TrajectoryDataset,
    TrajectoryTrace,
)
from umbral.application.agent_evals.trajectories.gate import evaluate_suite
from umbral.application.agent_evals.trajectories.loader import (
    load_trajectory_dataset,
)
from umbral.infrastructure.agent_evals.trajectory_executor import (
    PostgresTrajectoryExecutor,
)

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts" / "agent-evals" / "v2"


@pytest.fixture
def trajectory_backend(
    request: pytest.FixtureRequest,
) -> tuple[object, str]:
    """Postgres at head for one trajectory integration test."""
    connection: ServiceConnection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory, connection.url


def _seed_profile(factory, owner_id) -> object:
    from tests.integration.chat.conftest import seed_profile as _seed

    return _seed(factory, owner_id)


def _load_dataset() -> TrajectoryDataset:
    return load_trajectory_dataset(CONTRACTS / "conversation-trajectories-v2.json")


def test_trajectory_dataset_is_valid_and_covers_required_families(
    trajectory_backend: tuple[object, str],
) -> None:
    dataset = _load_dataset()
    families = {case.family for case in dataset.cases}
    required = {
        "radar_creation",
        "radar_refinement",
        "context_continuity",
        "multi_act",
        "correction",
        "preference_diversity",
        "transcription_regression",
        "query_safety",
    }
    assert required <= families
    assert len(dataset.cases) >= 8


def test_trajectory_suite_passes_the_strict_gate_over_postgres(
    trajectory_backend: tuple[object, str],
) -> None:
    factory, url = trajectory_backend
    dataset = _load_dataset()
    executor = PostgresTrajectoryExecutor(
        factory=factory,
        url=url,
        seed_user=seed_user,
        seed_profile=_seed_profile,
    )
    traces: dict[str, TrajectoryTrace] = {}
    failures: list[str] = []
    for case in dataset.cases:
        try:
            traces[case.id] = executor.execute(case=case)
            assert type(traces[case.id]) is TrajectoryTrace
            assert traces[case.id].case_id == case.id
        except Exception as exc:  # noqa: BLE001 - reported per case
            failures.append(f"{case.id}: {type(exc).__name__}: {exc}")

    suite = evaluate_suite(dataset=dataset, traces_by_case=traces, gate_enabled=False)

    assert failures == [], "execution failures: " + "; ".join(failures)
    if suite.blocked:
        for result in suite.case_results:
            failed = [
                f"{v.invariant_id}:{v.detail}"
                for v in result.invariant_verdicts
                if not v.passed
            ]
            if failed:
                print(f"CASE {result.case_id} ({result.family}) FAILED: {failed}")
                trace = traces[result.case_id]
                print(f"  states: {[s.state for s in trace.durable_states]}")
                print(f"  effects: {[e for e in trace.turn_effects]}")
                print(f"  verified: {trace.verified_target_ids}")
    assert suite.blocked is False, "; ".join(suite.reasons)
    for result in suite.case_results:
        assert result.success, f"{result.case_id} failed: " + "; ".join(
            f"{v.invariant_id}:{v.detail}"
            for v in result.invariant_verdicts
            if not v.passed
        )


def test_gate_is_strict_when_a_critical_invariant_fails(
    trajectory_backend: tuple[object, str],
) -> None:
    factory, url = trajectory_backend
    dataset = _load_dataset()
    executor = PostgresTrajectoryExecutor(
        factory=factory,
        url=url,
        seed_user=seed_user,
        seed_profile=_seed_profile,
    )
    traces: dict[str, TrajectoryTrace] = {}
    for case in dataset.cases:
        traces[case.id] = executor.execute(case=case)
    # A trace with a wrong-target mutation must block even with 95% success.
    first = dataset.cases[0]
    broken = TrajectoryTrace(
        case_id=first.id,
        turn_effects=(
            type(
                "E",
                (),
                {
                    "turn_index": 0,
                    "effect_key": "preference.remembered",
                    "status": "applied",
                    "confirmed": True,
                    "object_type": "preference",
                    "object_id": "wrong-radar",
                    "target_ids": ("p1",),
                },
            )(),
        ),
        verified_target_ids=("p1",),
    )
    traces[first.id] = broken

    suite = evaluate_suite(dataset=dataset, traces_by_case=traces, gate_enabled=False)

    assert suite.blocked is True
    assert any("wrong_target" in reason for reason in suite.reasons)
