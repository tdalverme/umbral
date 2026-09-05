"""Pure values and errors for persistent chat sessions and messages (H4.1)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

MessageRole = Literal["user", "assistant", "system"]
SessionStatus = Literal["active", "paused", "archived"]

_TEXT_KIND = "text"
_REPLY_KIND = "reply"


@dataclass(frozen=True, slots=True)
class ChatSession:
    """A durable conversation tied to a user; radar binding is optional.

    ``search_profile_id`` is None until the conversational service creates or
    binds the durable radar of the conversation (feature 016).
    """

    session_id: UUID
    user_id: UUID
    search_profile_id: UUID | None
    status: SessionStatus
    created_at: datetime
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """An immutable message with typed allowed content and run lineage."""

    message_id: UUID
    session_id: UUID
    role: MessageRole
    content: Mapping[str, object]
    state: str = "complete"
    graph_run_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now())
    correlation_id: UUID = field(default_factory=lambda: UUID(int=0))
    client_message_id: UUID | None = None


class ChatError(Exception):
    """Base class for sanitized chat failures."""

    code = "chat.error"


class ChatSessionNotFound(ChatError):
    """The session does not exist for the given user."""

    code = "chat.session_not_found"


class ChatSessionNotActive(ChatError):
    """The session's search profile is paused or archived; new turns are rejected."""

    code = "chat.session_not_active"


class ChatExecutionInProgress(ChatError):
    """A non-terminal run exists for the session; resume it before a new turn."""

    code = "chat.execution_in_progress"

    def __init__(self, run_id: UUID | None = None) -> None:
        self.run_id = run_id
        super().__init__("chat.execution_in_progress")


class ChatMessageTooLong(ChatError):
    """The message text exceeds the configured limit."""

    code = "chat.message_too_long"


class ChatValidationError(ChatError):
    """The message content violates the allowed-content contract."""

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        self.code = "chat.content_invalid"
        super().__init__(",".join(error_codes))


def is_message_role(value: object) -> bool:
    return value in {"user", "assistant", "system"}


def is_session_status(value: object) -> bool:
    return value in {"active", "paused", "archived"}


def validate_message_content(
    content: Mapping[str, object], *, max_text_length: int
) -> tuple[str, ...]:
    """Return content validation error codes, or an empty tuple when valid."""
    # ruff: noqa: E501
    errors: list[str] = []
    kind = content.get("kind")
    if kind == _TEXT_KIND:
        text = content.get("text")
        if not isinstance(text, str):
            errors.append("chat.content_missing_text")
        elif len(text) > max_text_length:
            errors.append("chat.message_too_long")
        context = content.get("context")
        if context is not None and not _valid_context(context):
            errors.append("chat.content_bad_context")
    elif kind == _REPLY_KIND:
        text = content.get("text")
        if not isinstance(text, str):
            errors.append("chat.content_missing_text")
        elif len(text) > max_text_length:
            errors.append("chat.message_too_long")
        refs = content.get("refs", [])
        if not isinstance(refs, list):
            errors.append("chat.content_bad_refs")
        else:
            for ref in refs:
                if not isinstance(ref, Mapping):
                    errors.append("chat.content_bad_refs")
                elif not isinstance(ref.get("entity"), str) or not isinstance(
                    ref.get("id"), str
                ):
                    errors.append("chat.content_bad_refs")
    else:
        errors.append("chat.content_kind")
    return tuple(errors)


def _valid_context(value: object) -> bool:
    """A bounded evidence scope: {entity, id} with entity in the allowed set."""
    if not isinstance(value, Mapping):
        return False
    entity = value.get("entity")
    ref_id = value.get("id")
    return (
        isinstance(entity, str)
        and entity in {"listing", "comparison"}
        and isinstance(ref_id, str)
        and bool(ref_id)
    )
