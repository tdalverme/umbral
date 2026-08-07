"""Public contracts for HTTP identities and sanitized problem details."""

from __future__ import annotations

import re
from contextlib import contextmanager
from importlib import import_module
from typing import Any, Iterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _runtime_app() -> FastAPI:
    try:
        main = import_module("umbral.api.main")
    except ModuleNotFoundError as error:
        pytest.fail(f"runtime API composition root is missing: {error.name}")

    app = getattr(main, "app", None)
    assert isinstance(app, FastAPI), "umbral.api.main must expose the FastAPI app"
    return app


@contextmanager
def _runtime_client() -> Iterator[TestClient]:
    """Exercise the composed API, never middleware or handlers in isolation."""

    app = _runtime_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def _assert_uuid(value: str) -> None:
    assert str(UUID(value)) == value


def _assert_identity_headers(response: Any) -> None:
    _assert_uuid(response.headers["x-request-id"])
    _assert_uuid(response.headers["x-correlation-id"])


def _assert_problem(response: Any) -> dict[str, object]:
    assert (
        response.headers["content-type"].split(";", 1)[0] == "application/problem+json"
    )
    assert 400 <= response.status_code <= 599
    _assert_identity_headers(response)

    payload = response.json()
    assert isinstance(payload, dict)
    assert {"type", "title", "status", "code", "request_id", "correlation_id"} <= set(
        payload
    )
    assert set(payload) <= {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
        "request_id",
        "correlation_id",
        "errors",
    }
    assert isinstance(payload["type"], str) and re.fullmatch(
        r"https?://.+", payload["type"]
    )
    assert isinstance(payload["title"], str) and len(payload["title"]) <= 200
    assert payload["status"] == response.status_code
    assert isinstance(payload["code"], str) and re.fullmatch(
        r"[a-z][a-z0-9_.-]{0,99}", payload["code"]
    )
    assert payload["request_id"] == response.headers["x-request-id"]
    assert payload["correlation_id"] == response.headers["x-correlation-id"]
    _assert_uuid(str(payload["request_id"]))
    _assert_uuid(str(payload["correlation_id"]))
    return payload


def test_every_request_receives_distinct_server_generated_identity_ids() -> None:
    with _runtime_client() as client:
        first = client.get("/health")
        second = client.get("/health")

    assert first.status_code == second.status_code == 200
    _assert_identity_headers(first)
    _assert_identity_headers(second)
    assert first.headers["x-request-id"] != second.headers["x-request-id"]
    assert first.headers["x-correlation-id"] != second.headers["x-correlation-id"]


def test_valid_correlation_id_is_preserved_and_is_not_the_request_id() -> None:
    correlation_id = "4b3d6b3c-0743-4d35-bc59-66063d24cd2b"

    with _runtime_client() as client:
        response = client.get("/health", headers={"X-Correlation-ID": correlation_id})

    assert response.status_code == 200
    _assert_identity_headers(response)
    assert response.headers["x-correlation-id"] == correlation_id
    assert response.headers["x-request-id"] != correlation_id


def test_problem_response_never_echoes_body_header_or_query_input() -> None:
    canary_body = "CANARY_BODY_DO_NOT_RETURN"
    canary_header = "CANARY_HEADER_DO_NOT_RETURN"
    canary_query = "CANARY_QUERY_DO_NOT_RETURN"

    with _runtime_client() as client:
        response = client.post(
            f"/health?secret={canary_query}",
            content=canary_body,
            headers={
                "Content-Type": "text/plain",
                "X-Canary-Header": canary_header,
                "X-Correlation-ID": "not-a-uuid",
            },
        )

    _assert_problem(response)
    serialized = response.text
    for canary in (canary_body, canary_header, canary_query, "not-a-uuid"):
        assert canary not in serialized


def test_problem_response_never_echoes_unexpected_exception_text() -> None:
    canary_exception = "CANARY_EXCEPTION_DO_NOT_RETURN"
    app = _runtime_app()

    @app.get("/_contract-test/unhandled-error", include_in_schema=False)
    def raise_unhandled_error() -> None:
        raise RuntimeError(canary_exception)

    route = app.router.routes[-1]
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/_contract-test/unhandled-error")
    finally:
        app.router.routes.remove(route)

    _assert_problem(response)
    assert canary_exception not in response.text
