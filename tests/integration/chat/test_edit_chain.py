# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Edit chain: derived proposal, superseded link and event emission (R-05, T025)."""

from __future__ import annotations

from uuid import UUID

from tests.integration.chat.test_hitl_lifecycle import (
    _Events,
    _build,
    USER_ID,
    SESSION_ID,
)


def test_edit_chain_emits_proposed_event_and_keeps_original() -> None:
    runtime, repo, _gateway = _build()
    first = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="subÃ­ el presupuesto a 900",
        correlation_id=UUID(int=40),
    )
    assert first.interrupt is not None
    original_id = UUID(str(first.interrupt["proposal_id"]))
    original_diff_before = dict(repo.proposals[original_id].diff)

    second = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="",
        correlation_id=UUID(int=41),
        resume=True,
        decision={"kind": "edit", "change": {"budget_max": 1100}},
    )
    assert second.interrupt is not None
    derived_id = UUID(str(second.interrupt["proposal_id"]))
    original = repo.proposals[original_id]
    # 0 reescrituras: the original diff is untouched.
    assert dict(original.diff) == original_diff_before
    assert original.state == "rejected"
    assert original.rejection_reason == "edited"
    assert original.superseded_by_proposal_id == derived_id
    assert repo.proposals[derived_id].state == "pending"
    assert repo.proposals[derived_id].diff == {"budget_max": 1100}


def test_edit_chain_second_approve_applies_derived_proposal() -> None:
    runtime, repo, _gateway = _build()
    first = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="subÃ­ el presupuesto a 900",
        correlation_id=UUID(int=40),
    )
    assert first.interrupt is not None
    original_id = UUID(str(first.interrupt["proposal_id"]))
    second = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="",
        correlation_id=UUID(int=41),
        resume=True,
        decision={"kind": "edit", "change": {"budget_max": 1100}},
    )
    assert second.interrupt is not None
    derived_id = UUID(str(second.interrupt["proposal_id"]))
    third = runtime.run_turn(
        user_id=USER_ID,
        session_id=SESSION_ID,
        text="",
        correlation_id=UUID(int=42),
        resume=True,
        decision={"kind": "approve", "idempotency_key": "decision-edit"},
    )
    assert third.status == "completed"
    assert repo.proposals[derived_id].state == "approved"
    assert repo.proposals[original_id].state == "rejected"
