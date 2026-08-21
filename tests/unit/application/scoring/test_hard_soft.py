"""US3: a confirmed hard criterion excludes candidates; soft only reorders."""

from __future__ import annotations

from uuid import UUID, uuid4

from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_compilation,
    build_observation,
)

from umbral.application.criteria.contracts import CompiledCriterion
from umbral.application.radar.contracts import SearchProfile
from umbral.application.silver.contracts import NormalizedListing

_CRITERION = CompiledCriterion


def _setup_balcon(
    context: ScoringTestContext,
) -> tuple[NormalizedListing, NormalizedListing, SearchProfile]:
    profile = build_profile()
    context.profiles.rows[profile.profile_id] = profile
    with_balcon = build_listing()
    without_balcon = build_listing()
    context.observations.observations = {
        with_balcon.listing_id: {
            "balcon": build_observation(
                listing_id=with_balcon.listing_id,
                concept_key="balcon",
                value="true",
            )
        },
        without_balcon.listing_id: {
            "balcon": build_observation(
                listing_id=without_balcon.listing_id,
                concept_key="balcon",
                value="false",
            )
        },
    }
    return with_balcon, without_balcon, profile


def test_hard_criterion_excludes_on_mismatch() -> None:
    context = ScoringTestContext()
    with_balcon, without_balcon, profile = _setup_balcon(context)
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(
            _CRITERION(
                concept_key="balcon",
                matcher_type="categorical",
                params={"allowed_values": ["true"]},
                source_ref="fact:test",
                soft_to_hard=True,
                weight=0.1,
            ),
        ),
    )
    scored = context.service.score_run(
        profile=profile,
        compilation=compilation,
        candidates=(with_balcon, without_balcon),
        run_id=uuid4(),
        correlation_id=uuid4(),
        score_policy_version=context.service.pin_policy_version(),
    )
    ids = {candidate.listing_id for candidate in scored}
    assert without_balcon.listing_id not in ids
    assert with_balcon.listing_id in ids


def test_soft_criterion_reorders_but_does_not_exclude() -> None:
    context = ScoringTestContext()
    with_balcon, without_balcon, profile = _setup_balcon(context)
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(
            _CRITERION(
                concept_key="balcon",
                matcher_type="categorical",
                params={"allowed_values": ["true"]},
                source_ref="fact:test",
                soft_to_hard=False,
                weight=0.1,
            ),
        ),
    )
    scored = context.service.score_run(
        profile=profile,
        compilation=compilation,
        candidates=(with_balcon, without_balcon),
        run_id=uuid4(),
        correlation_id=uuid4(),
        score_policy_version=context.service.pin_policy_version(),
    )
    ids = {candidate.listing_id for candidate in scored}
    assert with_balcon.listing_id in ids
    assert without_balcon.listing_id in ids


def test_hard_signal_criterion_excludes_below_threshold() -> None:
    context = ScoringTestContext()
    profile = build_profile()
    context.profiles.rows[profile.profile_id] = profile
    good = build_listing()
    bad = build_listing()
    context.observations.observations = {
        good.listing_id: {
            "acceso_escuela": build_observation(
                listing_id=good.listing_id,
                concept_key="acceso_escuela",
                value="signal",
                score=0.8,
                confidence=0.9,
            )
        },
        bad.listing_id: {
            "acceso_escuela": build_observation(
                listing_id=bad.listing_id,
                concept_key="acceso_escuela",
                value="signal",
                score=0.3,
                confidence=0.9,
            )
        },
    }
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(
            _CRITERION(
                concept_key="acceso_escuela",
                matcher_type="signal_score",
                params={
                    "signal_ref": "school_access",
                    "polarity": "positive",
                    "threshold": 0.6,
                },
                source_ref="fact:test",
                soft_to_hard=True,
                weight=0.1,
            ),
        ),
    )
    scored = context.service.score_run(
        profile=profile,
        compilation=compilation,
        candidates=(good, bad),
        run_id=uuid4(),
        correlation_id=uuid4(),
        score_policy_version=context.service.pin_policy_version(),
    )
    ids = {candidate.listing_id for candidate in scored}
    assert bad.listing_id not in ids
    assert good.listing_id in ids
