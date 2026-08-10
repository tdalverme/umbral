# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""Tools scope isolation over Postgres (FR-002, T046)."""

from __future__ import annotations

from uuid import uuid4

from tests.integration.agent.conftest import seed_profile, seed_user
from tests.integration.agent.tools.conftest import build_scope_stack
from tests.integration.chat.conftest import build_chat


def _create(chat, owner, profile):
    return chat.create_session(
        user_id=owner,
        search_profile_id=profile.profile_id,
        correlation_id=uuid4(),
    )


def test_foreign_user_session_is_denied(agent_backend) -> None:
    factory, _url = agent_backend
    owner = seed_user(factory)
    profile = seed_profile(factory, owner)
    chat = build_chat(factory)
    session = _create(chat, owner, profile)
    scope_reader = build_scope_stack(factory).scope_reader

    foreign = seed_user(factory)
    assert scope_reader.read_scope(foreign, session.session_id) is None

    owned = scope_reader.read_scope(owner, session.session_id)
    assert owned is not None
    assert owned.search_profile_id == profile.profile_id
    assert owned.status == "active"


def test_unknown_session_is_denied(agent_backend) -> None:
    factory, _url = agent_backend
    owner = seed_user(factory)
    scope_reader = build_scope_stack(factory).scope_reader
    assert scope_reader.read_scope(owner, uuid4()) is None
