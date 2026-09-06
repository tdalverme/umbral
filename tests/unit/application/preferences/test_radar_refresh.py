from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from umbral.application.preferences.contracts import PreferenceChange
from umbral.application.preferences.refresh import (
    RadarPreferenceRefreshCriteria,
    RadarPreferenceRefreshRadar,
    RadarPreferenceRefreshService,
)


class _Radar:
    def __init__(self) -> None:
        self.version_calls: list[dict[str, object]] = []
        self.schedule_calls: list[dict[str, object]] = []
        self.profile = SimpleNamespace(profile_id=uuid4(), owner_id=uuid4())
        self.version = SimpleNamespace(version_id=uuid4(), profile_version=2)
        self.run = SimpleNamespace(run_id=uuid4())

    def version_profile(self, **kwargs: object) -> tuple[object, object]:
        self.version_calls.append(kwargs)
        return self.profile, self.version

    def schedule_version_run(self, **kwargs: object) -> object:
        self.schedule_calls.append(kwargs)
        return self.run


class _Criteria:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.compilation = SimpleNamespace(compilation_id=uuid4())

    def compile_profile(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.compilation


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
