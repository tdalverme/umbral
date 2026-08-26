"""Unit tests for immutable V5 conversation contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import get_args

import pytest

from umbral.application.conversation.v5.contracts import (
    ClearFilter,
    ConversationActV5,
    CreateRadar,
    EvidenceSpan,
    ExpressDesire,
    Query,
    RecordFeedback,
    ResolvePending,
    ReviseDesire,
    SetFilter,
    TurnContextV5,
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
