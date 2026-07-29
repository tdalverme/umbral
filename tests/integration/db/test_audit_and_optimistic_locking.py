"""Audit values and optimistic locking contracts (T039)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from tests.fakes.transactions import InMemoryVersionedRecord

from umbral.domain.audit import AuditActor, AuditContext, RecordIdentity
from umbral.domain.errors import ConcurrencyConflict


def test_audit_values_require_actor_source_and_correlation() -> None:
    correlation_id = uuid4()
    identity = RecordIdentity.new(now=datetime.now(timezone.utc))
    actor = AuditActor.system()
    context = AuditContext(
        actor=actor, source="foundation.test", correlation_id=correlation_id
    )

    assert identity.version == 1
    assert identity.id
    assert context.actor.kind == "system"
    assert context.actor.id is None
    assert context.source == "foundation.test"
    assert context.correlation_id == correlation_id


def test_non_system_actor_requires_an_opaque_id() -> None:
    with pytest.raises(ValueError):
        AuditActor(kind="service", id=None)


def test_two_updates_with_same_version_yield_one_conflict() -> None:
    record = InMemoryVersionedRecord(value="initial")
    first = record.snapshot()
    second = record.snapshot()

    record.update(first.version, "first")
    with pytest.raises(ConcurrencyConflict) as raised:
        record.update(second.version, "second")

    assert raised.value.expected_version == 1
    assert raised.value.actual_version == 2
    assert record.value == "first"
