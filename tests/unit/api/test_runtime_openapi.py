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
        "identity_provider",
        "email_provider",
    ]


def test_runtime_openapi_publishes_environment_security_and_health_bypass() -> None:
    document = app.openapi()

    assert document["security"] == [{"environmentAccess": []}]
    assert document["components"]["securitySchemes"]["environmentAccess"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Environment-level operator or service identity. It is not a product "
            "user session or product authorization contract."
        ),
    }
    assert document["paths"]["/health"]["get"]["security"] == []


def test_runtime_openapi_documents_correlation_header_on_every_operation() -> None:
    document = app.openapi()

    for path_item in document["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            parameters = operation["parameters"]
            assert parameters == [
                {"$ref": "#/components/parameters/CorrelationId"}
            ]

    assert document["components"]["parameters"]["CorrelationId"] == {
        "name": "X-Correlation-ID",
        "in": "header",
        "required": False,
        "description": (
            "UUID for a multi-step operation. A valid value is preserved; "
            "when absent the runtime generates one."
        ),
        "schema": {"type": "string", "format": "uuid"},
    }


def test_runtime_openapi_documents_operational_headers_and_problem_responses() -> None:
    document = app.openapi()
    components = document["components"]

    assert components["headers"]["RequestId"] == {
        "description": "Server-generated UUID for this request",
        "schema": {"type": "string", "format": "uuid"},
    }
    assert components["headers"]["CorrelationId"] == {
        "description": "Preserved or server-generated operation UUID",
        "schema": {"type": "string", "format": "uuid"},
    }
    assert components["schemas"]["Problem"]["required"] == [
        "type",
        "title",
        "status",
        "code",
        "request_id",
        "correlation_id",
    ]
    assert components["schemas"]["ValidationIssue"]["required"] == [
        "field",
        "code",
    ]
    assert components["responses"] == {
        "Unauthorized": {
            "description": "Missing or invalid environment identity",
            "headers": {
                "X-Request-ID": {"$ref": "#/components/headers/RequestId"},
                "X-Correlation-ID": {
                    "$ref": "#/components/headers/CorrelationId"
                },
            },
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/Problem"}
                }
            },
        },
        "Forbidden": {
            "description": (
                "Valid environment identity without access to this environment"
            ),
            "headers": {
                "X-Request-ID": {"$ref": "#/components/headers/RequestId"},
                "X-Correlation-ID": {
                    "$ref": "#/components/headers/CorrelationId"
                },
            },
            "content": {
                "application/problem+json": {
                    "schema": {"$ref": "#/components/schemas/Problem"}
                }
            },
        },
    }

    for path in ("/health", "/ready", "/version"):
        response = document["paths"][path]["get"]["responses"]["200"]
        assert response["headers"] == {
            "Cache-Control": {
                "schema": {"type": "string", "const": "no-store"}
            },
            "X-Request-ID": {"$ref": "#/components/headers/RequestId"},
            "X-Correlation-ID": {"$ref": "#/components/headers/CorrelationId"},
        }

    readiness_responses = document["paths"]["/ready"]["get"]["responses"]
    assert readiness_responses["503"]["headers"] == {
        "Cache-Control": {
            "schema": {"type": "string", "const": "no-store"}
        },
        "Retry-After": {
            "schema": {"type": "integer", "minimum": 1, "maximum": 60}
        },
        "X-Request-ID": {"$ref": "#/components/headers/RequestId"},
        "X-Correlation-ID": {"$ref": "#/components/headers/CorrelationId"},
    }
    for path in ("/ready", "/version"):
        responses = document["paths"][path]["get"]["responses"]
        for status in ("401", "403"):
            component = "Unauthorized" if status == "401" else "Forbidden"
            assert responses[status] == {
                "$ref": f"#/components/responses/{component}"
            }
