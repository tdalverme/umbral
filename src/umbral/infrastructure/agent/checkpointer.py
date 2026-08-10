"""Postgres LangGraph checkpointer factory (UM-H4-003)."""

from __future__ import annotations

import os
import re
from typing import Any

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row

__all__ = ["create_postgres_saver", "close_postgres_saver", "LANGGRAPH_TABLES"]

# Library-managed tables; excluded from Alembic autogenerate/drift (R-03).
LANGGRAPH_TABLES = frozenset(
    {
        "checkpoint_migrations",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
    }
)


def create_postgres_saver(
    database_url: str, *, strict_msgpack: bool = True
) -> PostgresSaver:
    """Create a PostgresSaver with its tables, safe msgpack and a live connection.

    The saver owns a psycopg connection with ``autocommit=True`` and
    ``row_factory=dict_row`` as required by the library. Callers must close it
    with :func:`close_postgres_saver` when done.
    """
    # Guard against code execution from compromised checkpoint blobs (R-01).
    if strict_msgpack:
        os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    psycopg_url = re.sub(
        r"^postgres(ql)?\+psycopg://", "postgresql://", database_url, count=1
    )
    connection = psycopg.connect(psycopg_url, autocommit=True, row_factory=dict_row)
    saver = PostgresSaver(connection)
    saver.setup()
    return saver


def close_postgres_saver(saver: Any) -> None:
    """Close the connection owned by a saver created here, if still open."""
    conn = getattr(saver, "conn", None)
    if conn is not None:
        conn.close()
