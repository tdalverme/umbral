# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""find_matches tool tests (FR-013/FR-014, T032)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from tests.support.tools import (
    FakeRadar,
    FakeServices,
    build_executor,
    call_tool,
    payload,
)


def test_find_matches_returns_persisted_items_read_only() -> None:
    executor, services = build_executor()
    result = call_tool(executor, "find_matches", {"page": 1, "limit": 10})
    assert payload(result)["run_id"] == str(services.radar.run.run_id)
    assert payload(result)["stale"] is False
    assert payload(result)["total"] == 2
    items = cast(Any, payload(result)["items"])
    assert items[0]["listing_id"] == str(UUID(int=70))
    assert "score" in items[0]


def test_find_matches_is_strictly_read_only() -> None:
    executor, services = build_executor()
    call_tool(executor, "find_matches", {"page": 1, "limit": 10})
    assert services.radar.get_matches_calls == 1


def test_find_matches_no_run_declares_empty_stale_state() -> None:
    class NoRunRadar(FakeRadar):
        def get_matches(
            self,
            *,
            owner_id,
            profile_id,
            run_id,
            after_position,
            limit,
            include_dismissed=False,
        ):
            from umbral.application.radar.contracts import RunNotFound

            raise RunNotFound(profile_id)

    executor, _ = build_executor(services=FakeServices(radar=NoRunRadar()))
    result = call_tool(executor, "find_matches", {"page": 1, "limit": 10})
    assert result.status == "ok"
    assert result.result == {"run_id": None, "items": [], "total": 0, "stale": True}
