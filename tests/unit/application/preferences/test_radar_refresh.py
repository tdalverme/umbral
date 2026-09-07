from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from umbral.application.preferences.contracts import PreferenceChange
from umbral.application.preferences.refresh import (
    RadarPreferenceRefreshCriteria,
    RadarPreferenceRefreshRadar,
    RadarPreferenceRefreshService,
)
from umbral.domain.errors import ConcurrencyConflict


class _Radar:
    def __init__(self) -> None:
        self.version_calls: list[dict[str, object]] = []
        self.schedule_calls: list[dict[str, object]] = []
        self.version = SimpleNamespace(
            version_id=uuid4(),
            profile_version=2,
            correlation_id=uuid4(),
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        self.profile = SimpleNamespace(
            profile_id=uuid4(),
            owner_id=uuid4(),
            version=1,
            current_version_id=self.version.version_id,
        )
        self.run = SimpleNamespace(
            run_id=uuid4(), state="succeeded", job_execution_id=uuid4()
        )
        self.existing_run: object | None = None

    def version_profile(self, **kwargs: object) -> tuple[object, object]:
        self.version_calls.append(kwargs)
        return self.profile, self.version

    def schedule_version_run(self, **kwargs: object) -> object:
        self.schedule_calls.append(kwargs)
        return self.run

    def get_profile(self, owner_id: UUID, profile_id: UUID) -> object:
        del owner_id, profile_id
        return self.profile

    def list_active_profiles(self, limit: int) -> tuple[object, ...]:
        del limit
        return (self.profile,)

    def get_profile_version(self, **kwargs: object) -> object:
        del kwargs
        return self.version

    def get_run_for_version(self, **kwargs: object) -> object | None:
        del kwargs
        return self.existing_run


class _Criteria:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.compilation = SimpleNamespace(compilation_id=uuid4())
        self.existing_compilation: object | None = None
        self.facts_changed = False

    def compile_profile(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.compilation

    def latest_compilation(self, profile_version_id: UUID) -> object | None:
        del profile_version_id
        return self.existing_compilation

    def preference_facts_changed_since(
        self, profile_id: UUID, as_of: object
    ) -> bool:
        del profile_id, as_of
        return self.facts_changed


def _change(*, kind: str, fact_ids: tuple[UUID, ...] = ()) -> PreferenceChange:
    return PreferenceChange(
        expression=SimpleNamespace(expression_id=uuid4()),  # type: ignore[arg-type]
        bindings=(SimpleNamespace(kind=kind),),  # type: ignore[arg-type]
        fact_ids=fact_ids,
    )


def test_soft_change_versions_compiles_and_schedules_one_run() -> None:
    radar = _Radar()
    criteria = _Criteria()
    service = RadarPreferenceRefreshService(
        radar=cast(RadarPreferenceRefreshRadar, radar),
        criteria=cast(RadarPreferenceRefreshCriteria, criteria),
    )
    owner_id = uuid4()
    profile_id = uuid4()
    correlation_id = uuid4()

    result = service.refresh_after_change(
        owner_id=owner_id,
        profile_id=profile_id,
        expected_profile_version=1,
        changes=(
            _change(kind="structured", fact_ids=(uuid4(),)),
            _change(kind="semantic", fact_ids=(uuid4(),)),
        ),
        correlation_id=correlation_id,
        actor_id=str(owner_id),
    )

    assert result.refresh_state == "scheduled"
    assert result.run is not None
    assert result.run.run_id == radar.run.run_id
    assert len(radar.version_calls) == 1
    assert radar.version_calls[0]["owner_id"] == owner_id
    assert radar.version_calls[0]["profile_id"] == profile_id
    assert radar.version_calls[0]["expected_version"] == 1
    assert radar.version_calls[0]["changes"] == {}
    assert len(criteria.calls) == 1
    assert criteria.calls[0]["profile_version_id"] == radar.version.version_id
    assert len(radar.schedule_calls) == 1
    assert radar.schedule_calls[0]["trigger"] == "edited"


def test_unresolved_change_does_not_schedule_a_run() -> None:
    radar = _Radar()
    criteria = _Criteria()
    service = RadarPreferenceRefreshService(
        radar=cast(RadarPreferenceRefreshRadar, radar),
        criteria=cast(RadarPreferenceRefreshCriteria, criteria),
    )

    result = service.refresh_after_change(
        owner_id=uuid4(),
        profile_id=uuid4(),
        expected_profile_version=1,
        changes=(_change(kind="unresolved"),),
        correlation_id=uuid4(),
    )

    assert result.refresh_state == "not_required"
    assert result.run is None
    assert radar.version_calls == []
    assert criteria.calls == []


def test_unresolved_replacement_of_computable_preference_schedules_refresh() -> None:
    radar = _Radar()
    criteria = _Criteria()
    service = RadarPreferenceRefreshService(
        radar=cast(RadarPreferenceRefreshRadar, radar),
        criteria=cast(RadarPreferenceRefreshCriteria, criteria),
    )

    result = service.refresh_after_change(
        owner_id=uuid4(),
        profile_id=uuid4(),
        expected_profile_version=1,
        changes=(_change(kind="unresolved"),),
        previous_binding_kinds=("structured",),
        correlation_id=uuid4(),
    )

    assert result.refresh_state == "scheduled"
    assert len(radar.version_calls) == 1
    assert len(criteria.calls) == 1
    assert len(radar.schedule_calls) == 1


def test_refresh_retries_with_the_latest_profile_version_after_a_race() -> None:
    class _RetryRadar(_Radar):
        def version_profile(self, **kwargs: object) -> tuple[object, object]:
            if len(self.version_calls) == 0:
                self.version_calls.append(kwargs)
                raise ConcurrencyConflict(expected_version=1, actual_version=2)
            return super().version_profile(**kwargs)

        def get_profile(self, owner_id: UUID, profile_id: UUID) -> object:
            del owner_id, profile_id
            return SimpleNamespace(version=2)

    radar = _RetryRadar()
    criteria = _Criteria()
    service = RadarPreferenceRefreshService(
        radar=cast(RadarPreferenceRefreshRadar, radar),
        criteria=cast(RadarPreferenceRefreshCriteria, criteria),
    )

    result = service.refresh_after_change(
        owner_id=uuid4(),
        profile_id=uuid4(),
        expected_profile_version=1,
        changes=(_change(kind="structured", fact_ids=(uuid4(),)),),
        correlation_id=uuid4(),
    )

    assert result.refresh_state == "scheduled"
    assert len(radar.version_calls) == 2
    assert radar.version_calls[1]["expected_version"] == 2


def test_reconcile_repairs_a_version_without_compilation_or_run() -> None:
    radar = _Radar()
    criteria = _Criteria()
    service = RadarPreferenceRefreshService(
        radar=cast(RadarPreferenceRefreshRadar, radar),
        criteria=cast(RadarPreferenceRefreshCriteria, criteria),
    )

    repaired = service.reconcile_current_version(
        owner_id=radar.profile.owner_id,
        profile_id=radar.profile.profile_id,
    )

    assert repaired is True
    assert len(criteria.calls) == 1
    assert len(radar.schedule_calls) == 1
    assert radar.schedule_calls[0]["trigger"] == "edited"


def test_reconcile_pending_is_idempotent_when_version_is_complete() -> None:
    radar = _Radar()
    radar.existing_run = radar.run
    criteria = _Criteria()
    criteria.existing_compilation = criteria.compilation
    service = RadarPreferenceRefreshService(
        radar=cast(RadarPreferenceRefreshRadar, radar),
        criteria=cast(RadarPreferenceRefreshCriteria, criteria),
    )

    repaired = service.reconcile_pending(limit=10)

    assert repaired == 0
    assert criteria.calls == []
    assert radar.schedule_calls == []


def test_reconcile_repairs_a_pending_run_without_a_bound_job() -> None:
    radar = _Radar()
    radar.existing_run = SimpleNamespace(state="pending", job_execution_id=None)
    criteria = _Criteria()
    criteria.existing_compilation = criteria.compilation
    service = RadarPreferenceRefreshService(
        radar=cast(RadarPreferenceRefreshRadar, radar),
        criteria=cast(RadarPreferenceRefreshCriteria, criteria),
    )

    repaired = service.reconcile_current_version(
        owner_id=radar.profile.owner_id,
        profile_id=radar.profile.profile_id,
    )

    assert repaired is True
    assert criteria.calls == []
    assert len(radar.schedule_calls) == 1


def test_reconcile_versions_an_orphaned_preference_fact_before_repairing() -> None:
    radar = _Radar()
    criteria = _Criteria()
    criteria.existing_compilation = criteria.compilation
    criteria.facts_changed = True
    service = RadarPreferenceRefreshService(
        radar=cast(RadarPreferenceRefreshRadar, radar),
        criteria=cast(RadarPreferenceRefreshCriteria, criteria),
    )

    repaired = service.reconcile_current_version(
        owner_id=radar.profile.owner_id,
        profile_id=radar.profile.profile_id,
    )

    assert repaired is True
    assert len(radar.version_calls) == 1
    assert len(criteria.calls) == 1
    assert len(radar.schedule_calls) == 1
