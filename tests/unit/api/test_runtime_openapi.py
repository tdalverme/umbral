"""OpenAPI precision for the API runtime probe adapter."""

from __future__ import annotations

from umbral.api.main import app


def test_dependency_check_name_schema_is_the_closed_contract_allowlist() -> None:
    document = app.openapi()
    name_schema = document["components"]["schemas"]["DependencyCheck"]["properties"][
        "name"
    ]

    assert name_schema["enum"] == [
        "runtime_config",
        "api",
        "postgres",
        "schema",
        "postgis",
        "pgvector",
        "redis",
        "object_storage",
        "execution_loop",
        "scheduling_loop",
        "telemetry",
    ]
