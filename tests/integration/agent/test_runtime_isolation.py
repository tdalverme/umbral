"""Runtime isolation integration tests (US3, FR-007/SC-003)."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session
from tests.integration.agent.conftest import build_stack, create_session, seed_user

from umbral.application.chat.contracts import ChatSessionNotFound

SessionFactory = Callable[[], Session]
Backend = tuple[SessionFactory, str]


def test_cross_user_turn_is_denied_before_checkpoint_access(
    agent_backend: Backend,
) -> None:
    factory, url = agent_backend
    stack = build_stack(factory, url)
    owner = seed_user(factory)
    session = create_session(factory, owner)
    other = seed_user(factory)

    with pytest.raises(ChatSessionNotFound):
        stack.runtime.run_turn(
            user_id=other,
            session_id=session.session_id,
            text="x",
            correlation_id=uuid4(),
        )

    # The owner can still run normally.
    outcome = stack.runtime.run_turn(
        user_id=owner,
        session_id=session.session_id,
        text="hola",
        correlation_id=uuid4(),
    )
    assert outcome.status == "completed"
