# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""compare_listings tool tests (FR-017/FR-018, T036)."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from tests.support.tools import build_executor, call_tool, payload


def test_compare_listings_uses_structured_comparison() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "compare_listings",
        {"listing_ids": [str(UUID(int=70)), str(UUID(int=71))]},
    )
    assert payload(result)["dimensions"] == ["presupuesto"]
    comparison = cast(Any, payload(result)["comparison"])
    cells = cast(Any, comparison["cells"])
    assert cells[0]["listing_id"] == str(UUID(int=70))
    assert cells[0]["missing"] is False
    assert "winner" not in comparison


def test_compare_listings_rejects_malformed_args() -> None:
    executor, _ = build_executor()
    result = call_tool(executor, "compare_listings", {"listing_ids": "no-lista"})
    assert result.status == "error"
