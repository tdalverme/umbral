"""Unit tests for the persistent comparison shortlist (US10, P1)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from tests.support.radar import build_listing, build_profile
from tests.support.scoring import (
    ScoringTestContext,
    build_item,
    build_run,
)

from umbral.application.scoring.contracts import (
    ComparisonLimitExceeded,
    ComparisonNotInRadar,
    ScoringNotAccessible,
    ScoringStateError,
)


def _context_with_run(
    enabled: bool = True,
) -> tuple[ScoringTestContext, UUID, UUID, UUID]:
    context = ScoringTestContext(comparator_enabled=enabled)
    owner_id = uuid4()
    profile_id = uuid4()
    run_id = uuid4()
    listing = build_listing()
    context.runs.rows[run_id] = build_run(
        profile_id=profile_id, profile_version_id=uuid4(), run_id=run_id
    )
    context.items.items_by_run[run_id] = [build_item(run_id, listing.listing_id)]
    profile = build_profile(owner_id=owner_id, profile_id=profile_id)
    context.profiles.rows[profile_id] = profile
    return context, owner_id, profile_id, listing.listing_id


def test_shortlist_replaces_idempotently_and_survives_reload() -> None:
    context, owner_id, profile_id, listing_id = _context_with_run()
    stored = context.service.set_shortlist(
        owner_id=owner_id,
        profile_id=profile_id,
        listing_ids=(listing_id,),
        correlation_id=uuid4(),
    )
    assert stored == (listing_id,)
    assert context.service.get_shortlist(owner_id=owner_id, profile_id=profile_id) == (
        listing_id,
    )
    assert context.service.get_shortlist(owner_id=owner_id, profile_id=profile_id) == (
        listing_id,
    )


def test_over_limit_shortlist_is_rejected() -> None:
    context, owner_id, profile_id, _ = _context_with_run()
    with pytest.raises(ComparisonLimitExceeded):
        context.service.set_shortlist(
            owner_id=owner_id,
            profile_id=profile_id,
            listing_ids=tuple(uuid4() for _ in range(7)),
            correlation_id=uuid4(),
        )


def test_listing_outside_the_radar_is_rejected() -> None:
    context, owner_id, profile_id, _ = _context_with_run()
    with pytest.raises(ComparisonNotInRadar):
        context.service.set_shortlist(
            owner_id=owner_id,
            profile_id=profile_id,
            listing_ids=(uuid4(),),
            correlation_id=uuid4(),
        )


def test_cross_owner_access_is_denied() -> None:
    context, _, profile_id, listing_id = _context_with_run()
    with pytest.raises(ScoringNotAccessible):
        context.service.get_shortlist(owner_id=uuid4(), profile_id=profile_id)
    with pytest.raises(ScoringNotAccessible):
        context.service.set_shortlist(
            owner_id=uuid4(),
            profile_id=profile_id,
            listing_ids=(listing_id,),
            correlation_id=uuid4(),
        )


def test_disabled_comparator_rejects_writes() -> None:
    context, owner_id, profile_id, listing_id = _context_with_run(enabled=False)
    with pytest.raises(ScoringStateError):
        context.service.set_shortlist(
            owner_id=owner_id,
            profile_id=profile_id,
            listing_ids=(listing_id,),
            correlation_id=uuid4(),
        )
