"""Refresh the radar after a preference mutation changes scoring inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from umbral.application.criteria.contracts import Compilation
from umbral.application.preferences.contracts import PreferenceChange
from umbral.application.radar.contracts import (
    ProfileVersion,
    RecommendationRun,
    RecommendationRunTrigger,
    SearchProfile,
)
from umbral.domain.errors import ConcurrencyConflict

RefreshState = Literal["scheduled", "not_required"]


class RadarPreferenceRefreshRadar(Protocol):
    """Minimal radar surface needed to version and enqueue a refresh."""

    def get_profile(self, owner_id: UUID, profile_id: UUID) -> SearchProfile: ...

    def list_active_profiles(self, limit: int) -> tuple[SearchProfile, ...]: ...

    def get_profile_version(
        self, *, owner_id: UUID, profile_id: UUID, profile_version_id: UUID
    ) -> ProfileVersion | None: ...

    def get_run_for_version(
        self, *, owner_id: UUID, profile_id: UUID, profile_version_id: UUID
    ) -> RecommendationRun | None: ...

    def version_profile(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        expected_version: int,
        changes: Mapping[str, object],
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> tuple[SearchProfile, ProfileVersion]: ...

    def schedule_version_run(
        self,
        *,
        profile: SearchProfile,
        version: ProfileVersion,
        trigger: RecommendationRunTrigger,
    ) -> RecommendationRun | None: ...


class RadarPreferenceRefreshCriteria(Protocol):
    """Minimal criteria surface needed to compile the new profile snapshot."""

    def compile_profile(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        profile_version_id: UUID,
        edits: tuple[Mapping[str, object], ...],
        confirmations: tuple[str, ...] = (),
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> Compilation: ...

    def latest_compilation(self, profile_version_id: UUID) -> Compilation | None: ...

    def preference_facts_changed_since(
        self, profile_id: UUID, as_of: datetime
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class RadarPreferenceRefreshResult:
    """Durable artifacts produced by one preference-triggered refresh."""

    changes: tuple[PreferenceChange, ...]
    profile: SearchProfile | None
    profile_version: ProfileVersion | None
    compilation: Compilation | None
    run: RecommendationRun | None
    refresh_state: RefreshState


class RadarPreferenceRefreshService:
    """Coordinate preference changes with the versioned radar run lifecycle."""

    def __init__(
        self,
        *,
        radar: RadarPreferenceRefreshRadar,
        criteria: RadarPreferenceRefreshCriteria,
    ) -> None:
        self.radar = radar
        self.criteria = criteria

    def refresh_after_change(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        expected_profile_version: int,
        changes: tuple[PreferenceChange, ...],
        correlation_id: UUID,
        actor_kind: str = "user",
        actor_id: str | None = None,
        previous_binding_kinds: tuple[str, ...] = (),
    ) -> RadarPreferenceRefreshResult:
        """Create one new criteria snapshot and run when scoring can change.

        A preference without a computable binding is still durable, but cannot
        change the current ranking. The caller may pass the kinds retired by a
        revise operation so that changing a computable preference to an
        unresolved one still triggers a refresh.
        """
        if not _changes_affect_scoring(
            changes, previous_binding_kinds=previous_binding_kinds
        ):
            return RadarPreferenceRefreshResult(
                changes=changes,
                profile=None,
                profile_version=None,
                compilation=None,
                run=None,
                refresh_state="not_required",
            )

        profile: SearchProfile
        profile_version: ProfileVersion
        for attempt in range(2):
            try:
                profile, profile_version = self.radar.version_profile(
                    owner_id=owner_id,
                    profile_id=profile_id,
                    expected_version=expected_profile_version,
                    changes={},
                    correlation_id=correlation_id,
                    actor_kind=actor_kind,
                    actor_id=actor_id,
                )
                break
            except ConcurrencyConflict:
                if attempt == 1:
                    raise
                expected_profile_version = self.radar.get_profile(
                    owner_id, profile_id
                ).version
        compilation = self.criteria.compile_profile(
            owner_id=owner_id,
            profile_id=profile_id,
            profile_version_id=profile_version.version_id,
            edits=(),
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        run = self.radar.schedule_version_run(
            profile=profile,
            version=profile_version,
            trigger="edited",
        )
        return RadarPreferenceRefreshResult(
            changes=changes,
            profile=profile,
            profile_version=profile_version,
            compilation=compilation,
            run=run,
            refresh_state="scheduled",
        )

    def reconcile_current_version(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
    ) -> bool:
        """Repair an interrupted refresh or version an orphaned fact change."""

        profile = self.radar.get_profile(owner_id, profile_id)
        version_id = profile.current_version_id
        if version_id is None:
            return False
        version = self.radar.get_profile_version(
            owner_id=owner_id,
            profile_id=profile_id,
            profile_version_id=version_id,
        )
        if version is None:
            return False
        if self.criteria.preference_facts_changed_since(
            profile_id, version.created_at
        ):
            profile, version = self.radar.version_profile(
                owner_id=owner_id,
                profile_id=profile_id,
                expected_version=profile.version,
                changes={},
                correlation_id=uuid4(),
                actor_kind="service",
                actor_id=None,
            )
            self.criteria.compile_profile(
                owner_id=owner_id,
                profile_id=profile_id,
                profile_version_id=version.version_id,
                edits=(),
                correlation_id=version.correlation_id,
                actor_kind="service",
                actor_id=None,
            )
            latest_profile = self.radar.get_profile(owner_id, profile_id)
            if latest_profile.current_version_id != version.version_id:
                return False
            self.radar.schedule_version_run(
                profile=latest_profile,
                version=version,
                trigger="edited",
            )
            return True
        compilation = self.criteria.latest_compilation(version.version_id)
        run = self.radar.get_run_for_version(
            owner_id=owner_id,
            profile_id=profile_id,
            profile_version_id=version.version_id,
        )
        run_needs_job = run is not None and run.state in {
            "pending",
            "running",
        } and run.job_execution_id is None
        if compilation is not None and run is not None and not run_needs_job:
            return False
        if compilation is None:
            self.criteria.compile_profile(
                owner_id=owner_id,
                profile_id=profile_id,
                profile_version_id=version.version_id,
                edits=(),
                correlation_id=version.correlation_id,
                actor_kind="service",
                actor_id=None,
            )
        if run is None or run_needs_job:
            latest_profile = self.radar.get_profile(owner_id, profile_id)
            if latest_profile.current_version_id != version.version_id:
                return False
            self.radar.schedule_version_run(
                profile=latest_profile,
                version=version,
                trigger="edited",
            )
        return True

    def reconcile_pending(self, *, limit: int = 100) -> int:
        """Repair bounded active profiles after an interrupted refresh."""

        repaired = 0
        for profile in self.radar.list_active_profiles(limit):
            try:
                if self.reconcile_current_version(
                    owner_id=profile.owner_id,
                    profile_id=profile.profile_id,
                ):
                    repaired += 1
            except ConcurrencyConflict:
                # A concurrent request owns the refresh; its durable run or a
                # later scheduler pass will finish the repair.
                continue
        return repaired


def _changes_affect_scoring(
    changes: tuple[PreferenceChange, ...],
    *,
    previous_binding_kinds: tuple[str, ...],
) -> bool:
    computable_kinds = {"structured", "semantic"}
    return any(
        binding.kind in computable_kinds
        for change in changes
        for binding in change.bindings
    ) or any(kind in computable_kinds for kind in previous_binding_kinds)
