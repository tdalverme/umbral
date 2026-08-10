"""Agent eval suites, per-case results and run release stamp (H4.4).

Adds `agent_eval_suites` and `agent_eval_case_results` (persisted gate
results, R-08) and `agent_graph_runs.release_id` (each run references the
release that produced it, FR-010; 0 backfill mutation).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_agent_evals"
down_revision = "0011_chat_streaming"
branch_labels = None
depends_on = None


def _uuid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def _ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def _enum(name: str) -> postgresql.ENUM:
    values = {
        "eval_gateway_fidelity": ("simulated", "real"),
        "eval_suite_state": ("running", "passed", "blocked"),
        "eval_case_verdict": (
            "ok",
            "tool_selection_change",
            "args_change",
            "grounding_change",
            "confirmation_change",
            "outcome_change",
            "cost_delta",
            "latency_delta",
        ),
    }[name]
    return postgresql.ENUM(*values, name=name, create_type=False)


def _audit_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("created_at", _ts(), nullable=False),
        sa.Column("updated_at", _ts(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "actor_kind",
            postgresql.ENUM(
                "system", "service", "operator", name="actor_kind", create_type=False
            ),
            nullable=False,
            server_default="system",
        ),
        sa.Column("actor_id", sa.String(128)),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("correlation_id", _uuid(), nullable=False),
    ]


def _create_types() -> None:
    op.execute("CREATE TYPE eval_gateway_fidelity AS ENUM ('simulated', 'real')")
    op.execute("CREATE TYPE eval_suite_state AS ENUM ('running', 'passed', 'blocked')")
    op.execute(
        "CREATE TYPE eval_case_verdict AS ENUM "
        "('ok', 'tool_selection_change', 'args_change', 'grounding_change', "
        "'confirmation_change', 'outcome_change', 'cost_delta', 'latency_delta')"
    )


def _drop_types() -> None:
    op.execute("DROP TYPE IF EXISTS eval_case_verdict")
    op.execute("DROP TYPE IF EXISTS eval_suite_state")
    op.execute("DROP TYPE IF EXISTS eval_gateway_fidelity")


def upgrade() -> None:
    _create_types()
    op.create_table(
        "agent_eval_suites",
        *_audit_columns(),
        sa.Column("dataset_version", sa.String(120), nullable=False),
        sa.Column("baseline_release_id", sa.String(120), nullable=False),
        sa.Column("candidate_release_id", sa.String(120), nullable=True),
        sa.Column("gateway_fidelity", _enum("eval_gateway_fidelity"), nullable=False),
        sa.Column("status", _enum("eval_suite_state"), nullable=False),
        sa.Column("blocked_reasons", postgresql.JSONB(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=False),
        sa.Column("started_at", _ts(), nullable=False),
        sa.Column("finished_at", _ts(), nullable=True),
        sa.Index("ix_agent_eval_suites_created", "created_at"),
        sa.Index("ix_agent_eval_suites_release", "baseline_release_id"),
    )
    op.create_table(
        "agent_eval_case_results",
        *_audit_columns(),
        sa.Column(
            "eval_suite_id",
            _uuid(),
            sa.ForeignKey("agent_eval_suites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_id", sa.String(120), nullable=False),
        sa.Column("tool_selection_ok", sa.Boolean(), nullable=False),
        sa.Column("args_valid", sa.Boolean(), nullable=False),
        sa.Column("grounding_ok", sa.Boolean(), nullable=False),
        sa.Column("confirmation_ok", sa.Boolean(), nullable=False),
        sa.Column("outcome_ok", sa.Boolean(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("verdict", _enum("eval_case_verdict"), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Index("ix_agent_eval_case_results_suite", "eval_suite_id"),
    )
    op.add_column(
        "agent_graph_runs",
        sa.Column("release_id", sa.String(120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_graph_runs", "release_id")
    op.drop_table("agent_eval_case_results")
    op.drop_table("agent_eval_suites")
    _drop_types()
