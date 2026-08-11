# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Shared Postgres backend and eval executor for agent evals integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from tests.integration.chat.conftest import seed_profile
from tests.integration.radar.conftest import seed_user
from tests.support.containers import ServiceConnection

from umbral.application.agent_evals.context import load_conversation_contexts
from umbral.application.agent_evals.golden import load_golden_dataset
from umbral.application.agent_evals.price import load_price_table
from umbral.application.agent_evals.releases import load_releases
from umbral.infrastructure.agent_evals.composition import PostgresEvalCaseExecutor

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts" / "agent-evals" / "v1"


@pytest.fixture
def eval_backend(
    request: pytest.FixtureRequest,
) -> tuple[object, str]:
    """Postgres at head for one agent evals integration test."""
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


@pytest.fixture
def eval_context(eval_backend):
    factory, url = eval_backend
    dataset = load_golden_dataset(CONTRACTS / "conversations-golden-v1.json")
    releases = load_releases(
        CONTRACTS / "graph-releases-v1.json",
        known_case_ids={case.id for case in dataset.cases},
    )
    price_table = load_price_table(CONTRACTS / "price-table-v1.json")
    contexts = load_conversation_contexts(
        CONTRACTS / "conversation-context-v1.json",
        known_case_ids={case.id for case in dataset.cases},
    )
    context_map = {
        case_id: {
            "entity": context.entity,
            "id": context.id,
            "listing_ids": list(context.listing_ids),
        }
        for case_id, context in contexts.items()
    }
    executor = PostgresEvalCaseExecutor(
        factory=factory,
        url=url,
        seed_user=seed_user,
        seed_profile=seed_profile,
        contexts=context_map,
    )
    return dataclass_holder(factory, url, dataset, releases, price_table, executor)


def dataclass_holder(factory, url, dataset, releases, price_table, executor):
    from dataclasses import make_dataclass

    EvalContext = make_dataclass(
        "EvalContext",
        [
            ("factory", object),
            ("url", str),
            ("dataset", object),
            ("releases", object),
            ("price_table", object),
            ("executor", object),
        ],
    )
    return EvalContext(factory, url, dataset, releases, price_table, executor)
