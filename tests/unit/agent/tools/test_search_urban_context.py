# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""search_urban_context tool tests (FR-021, T040)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from tests.support.tools import build_executor, call_tool, payload


def test_search_urban_context_returns_versioned_signals_and_precision() -> None:
    executor, services = build_executor()
    result = call_tool(
        executor,
        "search_urban_context",
        {"listing_id": str(UUID(int=70)), "signal_types": []},
    )
    assert payload(result)["precision"] == "block"
    signals = cast(Any, payload(result)["signals"])
    assert signals[0]["signal_type"] == "transporte"
    assert signals[0]["signal_source"] == "osm"
    assert signals[0]["algorithm_version"] == "v1"


def test_search_urban_context_no_signals_declares_absence() -> None:
    from tests.support.tools import FakeCriteria, FakeServices, payload

    class EmptyCriteria(FakeCriteria):
        def list_urban_signals(self, listing_id):
            return ()

    executor, _ = build_executor(services=FakeServices(criteria=EmptyCriteria()))
    result = call_tool(
        executor,
        "search_urban_context",
        {"listing_id": str(UUID(int=70)), "signal_types": []},
    )
    assert payload(result)["signals"] == []
