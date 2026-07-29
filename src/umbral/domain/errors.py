"""Typed, transport-independent application failures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApplicationError(Exception):
    """A safe error contract suitable for transport adaptation."""

    code: str
    title: str
    status: int


class InvalidRequestError(ApplicationError):
    """A request violates a public runtime endpoint constraint."""

    def __init__(self) -> None:
        super().__init__(
            code="request.invalid",
            title="Invalid request",
            status=400,
        )


class InternalRuntimeError(ApplicationError):
    """An unexpected failure whose implementation details stay private."""

    def __init__(self) -> None:
        super().__init__(
            code="runtime.internal_error",
            title="Internal server error",
            status=500,
        )


class ConcurrencyConflict(ApplicationError):
    """A versioned update lost the optimistic-lock race."""

    def __init__(
        self,
        *,
        expected_version: int | None,
        actual_version: int | None,
    ) -> None:
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            code="concurrency.conflict",
            title="Concurrency conflict",
            status=409,
        )
