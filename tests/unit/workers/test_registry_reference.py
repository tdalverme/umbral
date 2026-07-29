from __future__ import annotations

from uuid import uuid4

import pytest

from umbral.application.jobs.contracts import JobContext
from umbral.application.jobs.reference import (
    FoundationReferenceHandler,
    InMemoryReferenceEffectRepository,
)
from umbral.workers.registry import JobRegistry


def test_registry_requires_explicit_canonical_handlers() -> None:
    handler = FoundationReferenceHandler()
    registry = JobRegistry({handler.job_type: handler})

    assert registry.types() == ("foundation.reference",)
    assert registry.normalize_target("foundation.reference", " ref:1 ") == "ref:1"
    with pytest.raises(KeyError):
        registry.require("unknown.job")


def test_reference_handler_effect_is_deterministic_and_idempotent() -> None:
    effects = InMemoryReferenceEffectRepository()
    handler = FoundationReferenceHandler(effects)
    context = JobContext(
        execution_id=uuid4(),
        attempt_number=1,
        correlation_id=uuid4(),
        release_id="test",
        logical_target="ref:1",
    )

    first = handler.run(context)
    second = handler.run(context)

    assert first == second
    assert len(effects.effects) == 1
