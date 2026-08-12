# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""get_listing_detail tool tests (listing data grounding)."""

from __future__ import annotations

from uuid import UUID

from tests.support.tools import build_executor, call_tool, payload


def test_get_listing_detail_returns_persisted_listing_data() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor, "get_listing_detail", {"listing_id": str(UUID(int=70))}
    )
    assert result.status == "ok"
    detail = payload(result)
    assert detail["neighborhood"] == "Palermo"
    assert detail["total_cost"] == 100000.0
    assert detail["price_currency"] == "ARS"
    assert detail["surface_m2"] == 55.0
    assert detail["rooms"] == 2
    assert detail["property_type"] == "departamento"


def test_get_listing_detail_denied_when_not_accessible() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor, "get_listing_detail", {"listing_id": str(UUID(int=999))}
    )
    assert result.status == "error"
    assert result.error_code == "tool.listing_not_accessible"


def test_get_listing_detail_requires_valid_uuid() -> None:
    executor, _ = build_executor()
    result = call_tool(executor, "get_listing_detail", {"listing_id": "no-uuid"})
    assert result.status == "error"
    assert result.error_code == "tool.args_invalid"
