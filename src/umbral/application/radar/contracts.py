"""Pure, transport-independent values and errors for the structured search radar."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

SearchProfileState = Literal["active", "paused", "archived"]
RecommendationRunState = Literal["pending", "running", "succeeded", "failed"]
RecommendationRunTrigger = Literal["created", "edited", "resumed"]
OperationType = Literal["rental"]


@dataclass(frozen=True, slots=True)
class SearchProfile:
    """Current state of one radar owned by a user."""

    profile_id: UUID
    owner_id: UUID
    name: str
    operation: OperationType
    zones: tuple[str, ...]
    budget_max: float | None
    budget_min: float | None
    min_rooms: int | None
    surface_min: float | None
    surface_max: float | None
    status: SearchProfileState
    unknown_strategy: Mapping[str, str]
    version: int
    created_at: datetime
    updated_at: datetime
    current_version_id: UUID | None
    latest_run_id: UUID | None
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None

    @property
    def budget_bound(self) -> float | None:
        return self.budget_max


@dataclass(frozen=True, slots=True)
class ProfileVersion:
    """Immutable snapshot of a profile consumed by recommendation runs."""

    version_id: UUID
    profile_id: UUID
    profile_version: int
    payload: Mapping[str, object]
    created_at: datetime
    correlation_id: UUID
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecommendationRun:
    """One executed run over a frozen profile version."""

    run_id: UUID
    profile_id: UUID
    profile_version_id: UUID
    state: RecommendationRunState
    trigger: RecommendationRunTrigger
    score_policy_version: str
    candidate_count: int
    published_item_count: int
    failure_code: str | None
    job_execution_id: UUID | None
    created_at: datetime
    finished_at: datetime | None
    correlation_id: UUID
    version: int = 1
    actor_kind: str = "service"
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class RecommendationItem:
    """Persistent, ordered match of one run."""

    item_id: UUID
    run_id: UUID
    listing_id: UUID
    score: float
    position: int
    contributions: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ListingSummary:
    """Card-level listing data of one match, without invented values."""

    listing_id: UUID
    total_cost: float
    neighborhood: str | None
    surface_m2: float | None
    rooms: int | None
    source_id: str
    url: str | None
    geo_precision: str


@dataclass(frozen=True, slots=True)
class MatchPoint:
    """Renderable point of one match, never more precise than authorized."""

    listing_id: UUID
    latitude: float
    longitude: float
    geo_precision: str


@dataclass(frozen=True, slots=True)
class MatchPage:
    """A stable page of persisted matches of one run."""

    run: RecommendationRun
    items: tuple[RecommendationItem, ...]
    next_after_position: int | None
    points: tuple[MatchPoint, ...] = ()
    summaries: tuple[ListingSummary, ...] = ()
    decision_states: Mapping[UUID, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ListingDetail:
    """Assembled detail view of a listing authorized through a user's runs."""

    listing_id: UUID
    source_id: str
    url: str | None
    neighborhood: str | None
    geo_precision: str
    total_cost: float
    price_value: float
    price_currency: str
    expenses_value: float | None
    surface_m2: float | None
    rooms: int | None
    bedrooms: int | None
    floor: int | None
    property_type: str
    amenities: tuple[str, ...]
    description_text: str | None
    normalization_errors: tuple[str, ...]
    known_changes: tuple[Mapping[str, object], ...]


class RadarError(Exception):
    """Base class for sanitized radar failures."""

    code = "radar.error"


class RadarValidationError(RadarError):
    """A profile draft violates the search-profile contract."""

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        self.code = "radar.validation_failed"
        super().__init__(",".join(error_codes))


class RadarNotFound(RadarError):
    code = "radar.not_found"

    def __init__(self, profile_id: UUID) -> None:
        self.profile_id = profile_id
        super().__init__(f"search profile not found: {profile_id}")


class RadarNotAccessible(RadarError):
    code = "radar.not_accessible"

    def __init__(self, profile_id: UUID) -> None:
        self.profile_id = profile_id
        super().__init__(f"search profile is not accessible: {profile_id}")


class RadarStateError(RadarError):
    code = "radar.state_invalid"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class RunNotFound(RadarError):
    code = "radar.run_not_found"

    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        super().__init__(f"recommendation run not found: {run_id}")


class ListingNotAccessible(RadarError):
    code = "radar.listing_not_accessible"

    def __init__(self, listing_id: UUID) -> None:
        self.listing_id = listing_id
        super().__init__(f"listing is not part of any accessible run: {listing_id}")


class RadarPermanentError(RadarError):
    """A terminal processing failure with an actionable code."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


class RadarTransientError(RadarError):
    """A bounded, retryable failure explicitly declared by the worker."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)
