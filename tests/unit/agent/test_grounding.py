# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Grounded refs: only tool-result refs persist, with cap (R-14, T029)."""

from __future__ import annotations

from typing import Any

from umbral.agent.graph import _tool_result_refs, _validated_refs

_STATE: dict[str, Any] = {
    "tool_results": [
        {
            "tool": "find_matches",
            "status": "ok",
            "result": {
                "items": [{"listing_id": "11111111-1111-1111-1111-111111111111"}]
            },
        },
        {
            "tool": "explain_match",
            "status": "ok",
            "result": {
                "listing_id": "22222222-2222-2222-2222-222222222222",
                "evidence_refs": [{"kind": "observation", "id": "obs-1"}],
            },
        },
        {
            "tool": "propose_search_profile_update",
            "status": "ok",
            "result": {"proposal_id": "33333333-3333-3333-3333-333333333333"},
        },
    ]
}


def test_tool_result_refs_collects_valid_entities() -> None:
    allowed = _tool_result_refs(_STATE)  # type: ignore[arg-type]
    assert "11111111-1111-1111-1111-111111111111" in allowed["listing"]
    assert "22222222-2222-2222-2222-222222222222" in allowed["listing"]
    assert "obs-1" in allowed["evidence_ref"]
    assert "33333333-3333-3333-3333-333333333333" in allowed["proposal"]


def test_foreign_or_invented_ref_is_dropped() -> None:
    valid, dropped = _validated_refs(
        _STATE,  # type: ignore[arg-type]
        [
            {"entity": "listing", "id": "11111111-1111-1111-1111-111111111111"},
            {"entity": "listing", "id": "99999999-9999-9999-9999-999999999999"},
            {"entity": "evidence_ref", "id": "inventada"},
            {"entity": "alien", "id": "x"},
        ],
        10,
    )
    assert dropped == 3
    assert valid == [
        {"entity": "listing", "id": "11111111-1111-1111-1111-111111111111"}
    ]


def test_ref_cap_is_enforced() -> None:
    refs = [
        {"entity": "listing", "id": "11111111-1111-1111-1111-111111111111"}
    ] * 15
    valid, dropped = _validated_refs(_STATE, refs, 10)  # type: ignore[arg-type]
    assert len(valid) == 10
    assert dropped == 5
