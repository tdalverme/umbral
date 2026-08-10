"""Pure regression runner over the golden dataset.

The runner invokes the real H3.2 scoring engine over each self-contained
golden case under two policy revisions (baseline and candidate) and applies the
strict gate of clarification 2026-08-09: any relative order change or hard
filter difference blocks unless a release in the registry declares exactly the
affected cases; score deltas without order change are informational (FR-004,
FR-005).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast
from uuid import UUID, uuid4, uuid5

from umbral.application.criteria.contracts import (
    Compilation,
    CompiledCriterion,
    ListingObservation,
)
from umbral.application.ingestion.contracts import SourceIdentity
from umbral.application.matching.contracts import (
    CaseVerdict,
    CaseVerdictItem,
    GoldenCase,
    GoldenDataset,
    HardFilterOutcome,
    MatchingError,
    RegressionReport,
    ReleasesRegistry,
)
from umbral.application.radar.contracts import SearchProfile
from umbral.application.scoring.engine import ScoredCandidate, score_candidates
from umbral.application.scoring.policy import ScoringPolicyDoc
from umbral.application.silver.contracts import GeoPrecision, NormalizedListing


class MatchingRegressionError(MatchingError):
    """A regression run could not be evaluated for a case."""

    code = "matching.regression_failed"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def run_regression(
    *,
    dataset: GoldenDataset,
    baseline_policy: ScoringPolicyDoc,
    candidate_policy: ScoringPolicyDoc,
    releases: ReleasesRegistry,
    now: datetime | None = None,
) -> RegressionReport:
    """Compare baseline vs candidate policy over every golden case.

    Returns a report with per-case verdicts and a gate decision. An order or
    hard-filter change is blocked unless declared by a release whose affected
    case ids match the detected diff exactly.
    """
    timestamp = now or datetime.now(timezone.utc)
    verdicts: list[CaseVerdictItem] = []
    changed_case_ids: set[str] = set()

    for case in dataset.cases:
        profile = _profile_from(case)
        listings = _listings_from(case)
        observations = _observations_from(case)
        compilation = _compilation_from(case, profile.profile_id, uuid4())
        run_id = uuid4()
        correlation_id = uuid4()

        baseline_scored = score_candidates(
            profile=profile,
            compilation=compilation,
            candidates=listings,
            observations=observations,
            policy=baseline_policy,
            run_id=run_id,
            correlation_id=correlation_id,
            now=timestamp,
        )
        candidate_scored = score_candidates(
            profile=profile,
            compilation=compilation,
            candidates=listings,
            observations=observations,
            policy=candidate_policy,
            run_id=run_id,
            correlation_id=correlation_id,
            now=timestamp,
        )
        passing_ids = frozenset(
            listing_id
            for listing_id, outcome in _hard_filter_outcomes(case, listings).items()
            if outcome == "pass"
        )
        baseline_order = tuple(
            item.listing_id
            for item in baseline_scored
            if str(item.listing_id) in passing_ids
            or _id_of(case, item.listing_id) in passing_ids
        )
        candidate_order = tuple(
            item.listing_id
            for item in candidate_scored
            if str(item.listing_id) in passing_ids
            or _id_of(case, item.listing_id) in passing_ids
        )
        expected_order = tuple(
            _listing_uuid(case, listing_id) for listing_id in case.expected_ranking
        )
        expected_filters = case.expected_hard_filter
        computed_filters = _hard_filter_outcomes(case, listings)

        verdict, detail, changed = _verdict_for(
            baseline_order=baseline_order,
            candidate_order=candidate_order,
            expected_order=expected_order,
            expected_filters=expected_filters,
            computed_filters=computed_filters,
            baseline_scores=baseline_scored,
            candidate_scores=candidate_scored,
            case=case,
        )
        verdicts.append(
            CaseVerdictItem(case_id=case.id, verdict=verdict, detail=detail)
        )
        if changed:
            changed_case_ids.add(case.id)

    declared = releases.affected_for(candidate_policy.score_policy_version)
    reasons = _gate_reasons(
        verdicts=tuple(verdicts),
        changed_case_ids=changed_case_ids,
        declared=declared,
    )
    return RegressionReport(
        dataset_version=dataset.registry_version,
        baseline_policy=baseline_policy.score_policy_version,
        candidate_policy=candidate_policy.score_policy_version,
        case_verdicts=tuple(verdicts),
        blocked=bool(reasons),
        reasons=reasons,
    )


def _verdict_for(
    *,
    baseline_order: tuple[UUID, ...],
    candidate_order: tuple[UUID, ...],
    expected_order: tuple[UUID, ...],
    expected_filters: Mapping[str, HardFilterOutcome],
    computed_filters: Mapping[str, HardFilterOutcome],
    baseline_scores: tuple[ScoredCandidate, ...],
    candidate_scores: tuple[ScoredCandidate, ...],
    case: GoldenCase,
) -> tuple[CaseVerdict, str, bool]:
    filter_mismatch = [
        f"{listing_id}:{expected_filters.get(listing_id, 'pass')}"
        f"!={computed_filters.get(listing_id, 'pass')}"
        for listing_id in sorted(set(expected_filters) | set(computed_filters))
        if expected_filters.get(listing_id, "pass")
        != computed_filters.get(listing_id, "pass")
    ]
    if filter_mismatch:
        return (
            "hard_filter_change",
            f"hard filter mismatch: {','.join(filter_mismatch)}",
            True,
        )
    if baseline_order != expected_order:
        return (
            "hard_filter_change",
            "baseline engine order differs from the reviewed expected order",
            True,
        )
    if baseline_order != candidate_order:
        return (
            "order_change",
            "order changed: "
            + ",".join(map(str, baseline_order))
            + " -> "
            + ",".join(map(str, candidate_order)),
            True,
        )
    if _scores_changed(baseline_scores, candidate_scores):
        return (
            "score_delta_informational",
            "scores changed without order change",
            False,
        )
    return ("ok", "no change", False)


def _scores_changed(
    baseline: tuple[ScoredCandidate, ...],
    candidate: tuple[ScoredCandidate, ...],
) -> bool:
    by_listing = {item.listing_id: item for item in baseline}
    return any(
        by_listing.get(item.listing_id) is None
        or by_listing[item.listing_id].score != item.score
        for item in candidate
    )


def _gate_reasons(
    *,
    verdicts: tuple[CaseVerdictItem, ...],
    changed_case_ids: set[str],
    declared: frozenset[str],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if changed_case_ids:
        undeclared = sorted(changed_case_ids - declared)
        extra = sorted(declared - changed_case_ids)
        if undeclared:
            reasons.append(f"matching.undeclared_change:{','.join(undeclared)}")
        if extra:
            reasons.append(f"matching.release_mismatch:{','.join(extra)}")
    for verdict in verdicts:
        if verdict.verdict == "hard_filter_change":
            reasons.append(
                f"matching.hard_filter_change:{verdict.case_id}:{verdict.detail}"
            )
    return tuple(dict.fromkeys(reasons))


def _hard_filter_outcomes(
    case: GoldenCase, listings: tuple[NormalizedListing, ...]
) -> Mapping[str, HardFilterOutcome]:
    profile = case.profile
    outcome: dict[str, HardFilterOutcome] = {}
    for golden in case.listings:
        listing_id = _listing_uuid(case, golden.listing_id)
        listing = next(item for item in listings if item.listing_id == listing_id)
        outcome[golden.listing_id] = _single_outcome(profile, listing)
    return outcome


def _single_outcome(profile: object, listing: NormalizedListing) -> HardFilterOutcome:
    budget_max = float(getattr(profile, "budget_max", 0.0))
    zones = tuple(str(zone).casefold() for zone in getattr(profile, "zones", ()))
    min_rooms = int(getattr(profile, "min_rooms", 0) or 0)
    if listing.total_cost > budget_max:
        return "excluded_budget"
    neighborhood = (listing.neighborhood or "").casefold()
    if neighborhood and zones and neighborhood not in zones:
        return "excluded_zone"
    if listing.rooms is not None and min_rooms and listing.rooms < min_rooms:
        return "excluded_rooms"
    return "pass"


def _id_of(case: GoldenCase, listing_uuid: UUID) -> str:
    for golden in case.listings:
        if _listing_uuid(case, golden.listing_id) == listing_uuid:
            return golden.listing_id
    return str(listing_uuid)


def _profile_from(case: GoldenCase) -> SearchProfile:
    profile = case.profile
    return SearchProfile(
        profile_id=uuid4(),
        owner_id=uuid4(),
        name=f"golden:{case.id}",
        operation="rental",
        zones=profile.zones,
        budget_max=profile.budget_max,
        budget_min=profile.budget_min,
        min_rooms=profile.min_rooms,
        surface_min=profile.surface_min,
        surface_max=profile.surface_max,
        status="active",
        unknown_strategy={
            "price": "exclude",
            "location": "exclude",
            "rooms": "include",
            "surface": "include",
        },
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_version_id=None,
        latest_run_id=None,
        correlation_id=uuid4(),
    )


def _listings_from(case: GoldenCase) -> tuple[NormalizedListing, ...]:
    listings: list[NormalizedListing] = []
    for golden in case.listings:
        listing_id = _listing_uuid(case, golden.listing_id)
        listings.append(
            NormalizedListing(
                listing_id=listing_id,
                canonical_property_id=uuid4(),
                run_id=uuid4(),
                snapshot_id=uuid4(),
                source=SourceIdentity(
                    source_id="golden", source_version="1", contract_version="1"
                ),
                external_id=golden.listing_id,
                url=None,
                published_at=None,
                last_observed_at=datetime.now(timezone.utc),
                normalizer_version="golden-v1",
                operation="rental",
                property_type="apartment",
                price_value=golden.total_cost,
                price_currency="ARS",
                expenses_value=None,
                expenses_currency=None,
                total_cost=golden.total_cost,
                price_assumptions={},
                surface_m2=golden.surface_m2,
                rooms=golden.rooms,
                bedrooms=None,
                floor=None,
                amenities=(),
                description_text=None,
                location_text="",
                neighborhood=golden.neighborhood,
                geo_precision=cast(GeoPrecision, golden.geo_precision),
                geometry=None,
                geo_source=None,
                normalization_errors=(),
            )
        )
    return tuple(listings)


def _observations_from(
    case: GoldenCase,
) -> Mapping[UUID, Mapping[str, ListingObservation]]:
    result: dict[UUID, Mapping[str, ListingObservation]] = {}
    for golden in case.listings:
        listing_id = _listing_uuid(case, golden.listing_id)
        observations: dict[str, ListingObservation] = {}
        for obs in golden.observations:
            observations[obs.concept_key] = ListingObservation(
                observation_id=uuid4(),
                listing_id=listing_id,
                concept_key=obs.concept_key,
                matcher_type="categorical",
                value=obs.value,
                score=obs.score,
                confidence=obs.confidence,
                evidence={"kind": "golden_case", "case_id": case.id},
                source="rule",
                extraction_version_id=None,
                state="active",
                failure_code=None,
                recomputation_run_id=None,
                created_at=datetime.now(timezone.utc),
                correlation_id=uuid4(),
            )
        result[listing_id] = observations
    return result


def _compilation_from(
    case: GoldenCase, profile_id: UUID, profile_version_id: UUID
) -> Compilation:
    criteria: list[CompiledCriterion] = []
    for criterion in case.criteria:
        criteria.append(
            CompiledCriterion(
                concept_key=criterion.concept_key,
                matcher_type=cast("object", criterion.matcher_type),  # type: ignore[arg-type]
                params=dict(criterion.params),
                source_ref=f"golden:{case.id}",
                soft_to_hard=False,
            )
        )
    return Compilation(
        compilation_id=uuid4(),
        profile_id=profile_id,
        profile_version_id=profile_version_id,
        compilation_version=1,
        criteria=tuple(criteria),
        warnings=(),
        confirmations=(),
        created_at=datetime.now(timezone.utc),
        correlation_id=uuid4(),
    )


_GOLDEN_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _listing_uuid(case: GoldenCase, listing_id: str) -> UUID:
    return uuid5(_GOLDEN_NAMESPACE, f"{case.id}:{listing_id}")
