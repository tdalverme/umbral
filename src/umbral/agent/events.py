"""Typed runtime events emitted while a graph run executes (FR-013)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RunStarted:
    run_id: UUID
    session_id: UUID
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class ReplyFragment:
    run_id: UUID
    delta: str


@dataclass(frozen=True, slots=True)
class ToolActivity:
    run_id: UUID
    tool: str
    status: str


@dataclass(frozen=True, slots=True)
class InterruptWaiting:
    """HITL: the run paused for an explicit decision on a durable proposal."""

    run_id: UUID
    interrupt: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RunCompleted:
    run_id: UUID
    message_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RunFailed:
    run_id: UUID
    error_code: str


@dataclass(frozen=True, slots=True)
class RunInterrupted:
    run_id: UUID


RuntimeEvent = (
    RunStarted
    | ReplyFragment
    | ToolActivity
    | InterruptWaiting
    | RunCompleted
    | RunFailed
    | RunInterrupted
)
