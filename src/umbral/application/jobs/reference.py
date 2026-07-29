"""The deterministic, side-effect-guarded foundation reference job."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid5

from .contracts import JobContext, JsonScalar, normalize_target

_REFERENCE_NAMESPACE = UUID("7b3f2f15-3b2e-4cb4-9d4e-38cba0fd9b9b")


class ReferenceEffectRepository(Protocol):
    def record_once(
        self, *, object_id: UUID, execution_id: UUID, target: str, correlation_id: UUID
    ) -> Mapping[str, JsonScalar]: ...


@dataclass(slots=True)
class InMemoryReferenceEffectRepository:
    effects: dict[UUID, dict[str, JsonScalar]]

    def __init__(self) -> None:
        self.effects = {}

    def record_once(
        self, *, object_id: UUID, execution_id: UUID, target: str, correlation_id: UUID
    ) -> Mapping[str, JsonScalar]:
        existing = self.effects.get(object_id)
        if existing is not None:
            return existing
        result: dict[str, JsonScalar] = {
            "object_id": str(object_id),
            "execution_id": str(execution_id),
            "target_digest": hashlib.sha256(target.encode()).hexdigest(),
            "correlation_id": str(correlation_id),
        }
        self.effects[object_id] = result
        return result


class FoundationReferenceHandler:
    job_type = "foundation.reference"

    def __init__(self, effects: ReferenceEffectRepository | None = None) -> None:
        self.effects = effects or InMemoryReferenceEffectRepository()

    def normalize_target(self, raw_target: str) -> str:
        return normalize_target(raw_target)

    def run(self, context: JobContext) -> Mapping[str, JsonScalar]:
        # The target is carried by the explicit registration/runtime seam; a
        # context intentionally contains no raw user payload. Local reference
        # runs use a deterministic execution target when no richer adapter is
        # composed.
        target = context.logical_target or f"execution:{context.execution_id}"
        object_id = uuid5(_REFERENCE_NAMESPACE, str(context.execution_id))
        return self.effects.record_once(
            object_id=object_id,
            execution_id=context.execution_id,
            target=target,
            correlation_id=context.correlation_id,
        )


def foundation_reference_registry() -> dict[str, FoundationReferenceHandler]:
    handler = FoundationReferenceHandler()
    return {handler.job_type: handler}
