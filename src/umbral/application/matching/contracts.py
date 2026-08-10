"""Pure, transport-independent values and errors for matching quality.

This module is test-only harness machinery (research R-06): it is never
imported by the API or workers and never reads the database at runtime.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

CaseTag = Literal[
    "hard_filter_violation",
    "unknown",
    "subjective_preference",
    "price_boundary",
    "legacy_no_breakdown",
]

HardFilterOutcome = Literal[
    "pass",
    "excluded_budget",
    "excluded_zone",
    "excluded_rooms",
]

CaseVerdict = Literal[
    "ok",
    "order_change",
    "hard_filter_change",
    "score_delta_informational",
]

ClaimVerdict = Literal["supported", "unsupported", "contradiction"]

_KNOWN_TAGS: frozenset[str] = frozenset(
    {
        "hard_filter_violation",
        "unknown",
        "subjective_preference",
        "price_boundary",
        "legacy_no_breakdown",
    }
)
_KNOWN_HARD_FILTERS: frozenset[str] = frozenset(
    {"pass", "excluded_budget", "excluded_zone", "excluded_rooms"}
)


@dataclass(frozen=True, slots=True)
class GoldenProfile:
    """The search profile inputs of one golden case."""

    zones: tuple[str, ...]
    budget_max: float
    budget_min: float | None
    min_rooms: int
    surface_min: float | None
    surface_max: float | None


@dataclass(frozen=True, slots=True)
class GoldenCriterion:
    """One compilation criterion of a golden case."""

    concept_key: str
    matcher_type: str
    params: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class GoldenObservation:
    """One extracted observation of a golden listing."""

    concept_key: str
    value: object
    score: float
    confidence: float


@dataclass(frozen=True, slots=True)
class GoldenListing:
    """One candidate listing of a golden case with its observations."""

    listing_id: str
    total_cost: float
    rooms: int | None
    surface_m2: float | None
    neighborhood: str | None
    geo_precision: str
    legacy: bool
    observations: tuple[GoldenObservation, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class GoldenCase:
    """One self-contained recommendation case with its expected order."""

    id: str
    tags: tuple[CaseTag, ...]
    profile: GoldenProfile
    criteria: tuple[GoldenCriterion, ...]
    listings: tuple[GoldenListing, ...]
    expected_ranking: tuple[str, ...]
    expected_hard_filter: Mapping[str, HardFilterOutcome]
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class GoldenDataset:
    """The versioned, product-reviewed golden recommendation dataset."""

    contract_version: str
    registry_version: str
    reviewed_by: str
    reviewed_at: str
    baseline_score_policy_version: str
    cases: tuple[GoldenCase, ...]

    def case_by_id(self, case_id: str) -> GoldenCase | None:
        return next((case for case in self.cases if case.id == case_id), None)


@dataclass(frozen=True, slots=True)
class Release:
    """One declared, explained scoring change."""

    id: str
    artifact: str
    artifact_version: str
    owner: str
    justification: str
    affected_case_ids: tuple[str, ...]
    date: str


@dataclass(frozen=True, slots=True)
class ReleasesRegistry:
    """Append-only registry of explained scoring changes."""

    contract_version: str
    registry_version: str
    releases: tuple[Release, ...]

    def affected_for(self, artifact_version: str) -> frozenset[str]:
        return frozenset(
            case_id
            for release in self.releases
            if release.artifact_version == artifact_version
            for case_id in release.affected_case_ids
        )


@dataclass(frozen=True, slots=True)
class ForbiddenConcept:
    """One forbidden concept with its justification."""

    concept_key: str
    justification: str


@dataclass(frozen=True, slots=True)
class ForbiddenProxy:
    """One forbidden proxy feature with its justification."""

    proxy_key: str
    justification: str


@dataclass(frozen=True, slots=True)
class ForbiddenFeatures:
    """Machine-checkable output of the fairness review."""

    contract_version: str
    registry_version: str
    forbidden_concepts: tuple[ForbiddenConcept, ...]
    forbidden_proxies: tuple[ForbiddenProxy, ...]
    normative_phrases: tuple[str, ...]

    def is_forbidden_concept(self, concept_key: str) -> bool:
        return any(item.concept_key == concept_key for item in self.forbidden_concepts)


@dataclass(frozen=True, slots=True)
class CaseVerdictItem:
    """Per-case verdict of a regression run."""

    case_id: str
    verdict: CaseVerdict
    detail: str


@dataclass(frozen=True, slots=True)
class RegressionReport:
    """Result of one regression over the golden dataset."""

    dataset_version: str
    baseline_policy: str
    candidate_policy: str
    case_verdicts: tuple[CaseVerdictItem, ...]
    blocked: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FidelityClaim:
    """One asserted claim of an explanation to classify against the breakdown."""

    criterion_key: str
    asserted_state: str | None
    evidence_refs: tuple[Mapping[str, object], ...]
    text: str


@dataclass(frozen=True, slots=True)
class ClaimVerdictItem:
    """Per-claim verdict of a fidelity evaluation."""

    criterion_key: str
    verdict: ClaimVerdict
    detail: str


@dataclass(frozen=True, slots=True)
class FidelityReport:
    """Result of one fidelity evaluation of explanations."""

    passing: bool
    claims: tuple[ClaimVerdictItem, ...]
    missing_uncertainty: tuple[str, ...]
    no_breakdown_items: tuple[str, ...]
    reasons: tuple[str, ...]


class MatchingError(Exception):
    """Base class for sanitized matching quality failures."""

    code = "matching.error"


class MatchingValidationError(MatchingError):
    """A matching contract document violates its declared shape."""

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        self.code = "matching.validation_failed"
        super().__init__(",".join(error_codes))


class RegressionBlocked(MatchingError):
    """The regression gate blocks an unexplained change."""

    code = "matching.regression_blocked"

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))
