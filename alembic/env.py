"""Alembic environment with offline and online metadata checks."""

from __future__ import annotations

import os
import re
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from umbral.infrastructure.db.migrations import expected_schema

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("DATABASE_URL")
if database_url:
    database_url = re.sub(
        r"^postgres(ql)?://", "postgresql+psycopg://", database_url, count=1
    )
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = expected_schema()

_LANGGRAPH_TABLES = frozenset(
    {
        "checkpoint_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
    }
)


def _include_object(
    object_: object,
    name: str,
    type_: str,
    reflected: bool,
    compare_to: object,
) -> bool:
    """Exclude LangGraph-managed checkpoint tables from autogenerate/drift."""
    # ruff: noqa: ARG002
    if type_ == "table":
        return name not in _LANGGRAPH_TABLES
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=_include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
