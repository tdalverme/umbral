from __future__ import annotations

# ruff: noqa: E501
import importlib.util
from pathlib import Path

from umbral.infrastructure.db.migrations import expected_schema


def test_identity_revision_is_linear_and_metadata_has_all_tables() -> None:
    path = Path(__file__).parents[2] / "alembic" / "versions" / "0002_private_beta_identity.py"
    spec = importlib.util.spec_from_file_location("identity_revision", path)
    assert spec and spec.loader
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    assert revision.revision == "0002_private_beta_identity"
    assert revision.down_revision == "0001_foundation_runtime"
    tables = set(expected_schema().tables)
    assert {
        "identity_invitations",
        "product_users",
        "external_identity_links",
        "role_assignments",
        "magic_link_requests",
        "magic_link_attempts",
        "product_sessions",
        "access_audit_events",
    } <= tables
