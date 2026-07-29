"""Public contract for the side-effect-free runtime probe endpoints."""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import datetime
from importlib import import_module
from typing import Any, Iterator, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@contextmanager
def _runtime_client() -> Iterator[TestClient]:
    """Exercise the composed API, never route handlers in isolation."""

    try:
        main = import_module("umbral.api.main")
    except ModuleNotFoundError as error:
        pytest.fail(f"runtime API composition root is missing: {error.name}")

    app = getattr(main, "app", None)
    assert isinstance(app, FastAPI), "umbral.api.main must expose the FastAPI app"
    with TestClient(app) as client:
        yield client


def _assert_common_headers(response: Any) -> None:
    assert response.headers["content-type"].split(";", 1)[0] == "application/json"
    assert response.headers["cache-control"] == "no-store"


def _assert_readiness_schema(payload: object) -> None:
    assert isinstance(payload, dict)
    assert set(payload) == {"surface", "state", "observed_at", "release_id", "checks"}
    assert payload["surface"] in {"web", "api", "worker", "scheduler"}
    assert payload["state"] in {"ready", "degraded", "not_ready"}
    assert isinstance(payload["release_id"], str) and payload["release_id"]
    assert isinstance(payload["checks"], list) and len(payload["checks"]) <= 12
    datetime.fromisoformat(cast(str, payload["observed_at"]).replace("Z", "+00:00"))
    for check in payload["checks"]:
        assert isinstance(check, dict)
        assert set(check) <= {"name", "state", "critical", "code"}
        assert {"name", "state", "critical"} <= set(check)
        assert check["state"] in {"ready", "degraded", "unavailable"}
        assert isinstance(check["critical"], bool)
        if "code" in check:
            assert re.fullmatch(r"[a-z][a-z0-9_.-]{0,99}", check["code"])


def _assert_version_schema(payload: object) -> None:
    assert isinstance(payload, dict)
    assert set(payload) == {
        "surface",
        "release_id",
        "git_sha",
        "artifact_digest",
        "manifest_sha256",
        "contract_major",
        "database_revision",
        "built_at",
    }
    assert payload["surface"] in {"web", "api", "worker", "scheduler"}
    assert isinstance(payload["release_id"], str) and payload["release_id"]
    assert re.fullmatch(r"[0-9a-f]{40}", payload["git_sha"])
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", payload["artifact_digest"])
    assert re.fullmatch(r"[0-9a-f]{64}", payload["manifest_sha256"])
    assert payload["contract_major"] == 1
    assert isinstance(payload["database_revision"], str)
    assert payload["database_revision"]
    datetime.fromisoformat(cast(str, payload["built_at"]).replace("Z", "+00:00"))


def test_health_is_alive_and_has_no_observable_effect_on_repeated_requests() -> None:
    with _runtime_client() as client:
        first = client.get("/health")
        second = client.get("/health")

    assert first.status_code == second.status_code == 200
    _assert_common_headers(first)
    _assert_common_headers(second)
    assert first.json() == second.json() == {"status": "alive"}


def test_health_rejects_unexpected_query_parameters_without_echoing_input() -> None:
    canary = "unexpected-query-canary"
    with _runtime_client() as client:
        response = client.get(f"/health?probe={canary}")

    assert response.status_code in {400, 422}
    assert canary not in response.text


def test_ready_repeated_requests_preserve_state_without_durable_effects() -> None:
    with _runtime_client() as client:
        first = client.get("/ready")
        second = client.get("/ready")

    for response in (first, second):
        payload = response.json()
        _assert_common_headers(response)
        _assert_readiness_schema(payload)
        expected_status = 503 if payload["state"] == "not_ready" else 200
        assert response.status_code == expected_status
        if expected_status == 503:
            assert 1 <= int(response.headers["retry-after"]) <= 60

    first_payload = first.json()
    second_payload = second.json()
    first_payload.pop("observed_at")
    second_payload.pop("observed_at")
    assert first_payload == second_payload


def test_version_identifies_immutable_runtime_release_without_writing_state() -> None:
    with _runtime_client() as client:
        first = client.get("/version")
        second = client.get("/version")

    assert first.status_code == second.status_code == 200
    _assert_common_headers(first)
    _assert_common_headers(second)
    _assert_version_schema(first.json())
    assert second.json() == first.json()
