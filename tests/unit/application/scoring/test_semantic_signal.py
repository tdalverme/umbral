"""Semantic signals are bounded soft contributions, never hard filters."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    build_compilation,
)

from umbral.application.scoring.contracts import SemanticSignal
from umbral.application.scoring.engine import score_candidates
from umbral.application.scoring.policy import parse_policy_document
from umbral.infrastructure.criteria.contract_loader import load_matcher_types
from umbral.infrastructure.scoring.contract_loader import load_scoring_policy_seed

_NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def _signal(listing_id: UUID, score: float, confidence: float = 1.0) -> SemanticSignal:
    return SemanticSignal(
        binding_id=uuid4(),
        listing_id=listing_id,
        score=score,
        confidence=confidence,
        query_embedding_ref=uuid4(),
        listing_embedding_ref=uuid4(),
    )


def test_semantic_signal_contributes_only_softly_and_capped() -> None:
    profile = build_profile()
    listing = build_listing(total_cost=700.0)
    compilation = build_compilation(
        profile_id=profile.profile_id,
        profile_version_id=uuid4(),
        criteria=(),
    )
    policy = parse_policy_document(
        load_scoring_policy_seed(), load_matcher_types()
    )
    # Force a v2 semantic block on the parsed seed for the bounded path.
    from dataclasses import replace

    from umbral.application.scoring.policy import SemanticPolicy

    policy = replace(
        policy,
        contract_version="2",
        semantic=SemanticPolicy(
            mode="soft", max_weight=0.10, missing_evidence_contribution=0.0
        ),
    )

    with_signal = score_candidates(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        observations={},
        policy=policy,
        run_id=uuid4(),
        correlation_id=uuid4(),
        now=_NOW,
        semantic_signals={
            listing.listing_id: (_signal(listing.listing_id, 1.0),)
        },
    )[0]
    without = score_candidates(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        observations={},
        policy=policy,
        run_id=uuid4(),
        correlation_id=uuid4(),
        now=_NOW,
        semantic_signals={},
    )[0]

    # Perfect semantic evidence moves the score by at most the 0.10 cap.
    assert with_signal.score <= 1.0
    assert with_signal.score > without.score
    assert round(with_signal.score - without.score, 6) <= 0.10


def test_semantic_signal_without_policy_block_contributes_zero() -> None:
    profile = build_profile()
    listing = build_listing()
    compilation = build_compilation(
        profile_id=profile.profile_id, profile_version_id=uuid4(), criteria=()
    )
    policy = parse_policy_document(
        load_scoring_policy_seed(), load_matcher_types()
    )
    # Seed policy v1 has no semantic block (contract_version == 1).

    with_signal = score_candidates(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        observations={},
        policy=policy,
        run_id=uuid4(),
        correlation_id=uuid4(),
        now=_NOW,
        semantic_signals={
            listing.listing_id: (_signal(listing.listing_id, 0.9),)
        },
    )[0]
    without = score_candidates(
        profile=profile,
        compilation=compilation,
        candidates=(listing,),
        observations={},
        policy=policy,
        run_id=uuid4(),
        correlation_id=uuid4(),
        now=_NOW,
        semantic_signals={},
    )[0]

    assert with_signal.score == without.score


def test_zero_or_missing_signals_never_exclude_a_candidate() -> None:
    """Soft preferences must not eliminate candidates that pass hard filters."""
    profile = build_profile()
    candidate = build_listing(total_cost=900.0)
    compilation = build_compilation(
        profile_id=profile.profile_id, profile_version_id=uuid4(), criteria=()
    )
    policy = parse_policy_document(
        load_scoring_policy_seed(), load_matcher_types()
    )

    with_weak_signal = score_candidates(
        profile=profile,
        compilation=compilation,
        candidates=(candidate,),
        observations={},
        policy=policy,
        run_id=uuid4(),
        correlation_id=uuid4(),
        now=_NOW,
        semantic_signals={
            candidate.listing_id: (
                _signal(candidate.listing_id, 0.0, confidence=0.0),
            )
        },
    )[0]
    without = score_candidates(
        profile=profile,
        compilation=compilation,
        candidates=(candidate,),
        observations={},
        policy=policy,
        run_id=uuid4(),
        correlation_id=uuid4(),
        now=_NOW,
        semantic_signals={},
    )[0]

    assert with_weak_signal.listing_id == candidate.listing_id
    assert with_weak_signal.score == without.score