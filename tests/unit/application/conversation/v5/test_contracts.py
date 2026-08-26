"""Unit tests for immutable V5 conversation contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import cast, get_args, get_type_hints

import pytest

from umbral.application.conversation.v5.contracts import (
    ClearFilter,
    CommandV5,
    ConversationActV5,
    CreateRadar,
    EvidenceSpan,
    ExpressDesire,
    FilterKeyV5,
    FilterValueV5,
    HardFilterV5,
    Query,
    RecordFeedback,
    ResolvePending,
    ReviseDesire,
    SetFilter,
    TurnContextV5,
    TurnPlanV5,
    UnsupportedRequest,
    WithdrawDesire,
)


def test_evidence_span_rejects_invalid_boundaries() -> None:
    """Bad offsets would let policy treat non-message text as evidence."""
    with pytest.raises(ValueError):
        EvidenceSpan(start=-1, end=0, text="x")
    with pytest.raises(ValueError):
        EvidenceSpan(start=2, end=1, text="x")


def test_contract_dataclasses_are_frozen_and_slotted() -> None:
    """Mutable or dictionary-backed act state would violate the contract boundary."""
    span = EvidenceSpan(start=0, end=1, text="x")
    act = Query(
        act_id="act-1",
        confidence=0.9,
        evidence_spans=(span,),
        query_text="mostrar resultados",
    )

    with pytest.raises(FrozenInstanceError):
        act.query_text = "otra consulta"  # type: ignore[misc]
    assert not hasattr(act, "__dict__")


def test_turn_context_authorizes_only_references_in_its_snapshot() -> None:
    """Reference authorization must not infer access by parsing opaque refs."""
    context = TurnContextV5(
        user_id="user:1",
        session_id="session:1",
        active_radar_ref="radar:1",
        active_radar_version=2,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=("listing:13",),
        allowed_capabilities=("query",),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id="correlation:1",
    )

    assert context.authorizes("listing:13")
    assert not context.authorizes("listing:99")


def test_act_union_is_exhaustive_and_ordered() -> None:
    """A reordered or widened union could change exhaustive policy dispatch."""
    assert get_args(ConversationActV5) == (
        CreateRadar,
        SetFilter,
        ClearFilter,
        ExpressDesire,
        ReviseDesire,
        WithdrawDesire,
        RecordFeedback,
        ResolvePending,
        Query,
        UnsupportedRequest,
    )


@pytest.mark.parametrize(
    ("filter_key", "value"),
    [
        ("budget_max", 1200.0),
        ("min_rooms", 2),
        ("zones", ("palermo", "belgrano")),
    ],
)
def test_hard_filter_values_match_the_published_types(
    filter_key: FilterKeyV5, value: FilterValueV5
) -> None:
    """Python contracts must accept precisely the values published in JSON."""
    filter_view = HardFilterV5(
        filter_key=filter_key,
        value=value,
    )

    assert filter_view.value == value


@pytest.mark.parametrize(
    ("filter_key", "value"),
    [
        ("budget_max", ("1200",)),
        ("min_rooms", 2.5),
        ("zones", ("palermo", 3)),
        ("unknown", ("palermo",)),
    ],
)
def test_hard_filter_rejects_values_outside_the_published_types(
    filter_key: FilterKeyV5, value: object
) -> None:
    """Mismatched Python values must fail at the same boundary as JSON values."""
    with pytest.raises(ValueError):
        HardFilterV5(
            filter_key=filter_key,
            value=cast(FilterValueV5, value),
        )


@pytest.mark.parametrize(
    "value",
    [
        ("",),
        tuple(f"zone-{index}" for index in range(16)),
    ],
)
def test_hard_filter_rejects_zones_outside_the_published_constraints(
    value: tuple[str, ...],
) -> None:
    """Python zone filters must match JSON's non-empty, fifteen-zone limit."""
    with pytest.raises(ValueError):
        HardFilterV5(filter_key="zones", value=value)


@pytest.mark.parametrize(
    ("filter_key", "value"),
    [
        ("budget_max", ("1200",)),
        ("min_rooms", 2.5),
        ("zones", ("",)),
        ("zones", tuple(f"zone-{index}" for index in range(16))),
    ],
)
def test_set_filter_rejects_values_outside_the_published_constraints(
    filter_key: FilterKeyV5, value: object
) -> None:
    """Set-filter acts must enforce the same scalar and zone constraints."""
    with pytest.raises(ValueError):
        SetFilter(
            act_id="act-1",
            confidence=0.9,
            evidence_spans=(EvidenceSpan(start=0, end=1, text="x"),),
            filter_key=filter_key,
            value=cast(FilterValueV5, value),
        )


def test_turn_plan_commands_use_the_closed_union() -> None:
    """Commands are typed by the published closed command union."""
    assert get_type_hints(TurnPlanV5)["commands"] == tuple[CommandV5, ...]


def test_turn_plan_accepts_only_commanded_payloads_at_runtime() -> None:
    """Commands must be members of the closed command union, not open objects."""
    with pytest.raises(ValueError):
        TurnPlanV5(
            decisions=(),
            commands=cast(tuple[CommandV5, ...], (object(),)),
        )
