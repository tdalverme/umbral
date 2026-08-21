"""US5: automatic invalidation scopes and manual recompute orchestration."""

from __future__ import annotations

from uuid import UUID, uuid4

from tests.support.criteria import CriteriaTestContext

from umbral.application.criteria.contracts import RecomputeScope


def _seed_with_listings(context: CriteriaTestContext, texts: list[str]) -> None:
    context.seed_concepts()
    for text in texts:
        context.add_listing(description_text=text)


def test_register_extraction_version_invalidates_previous_observations() -> None:
    context = CriteriaTestContext()
    _seed_with_listings(context, ["con balcon", "sin balcon"])
    context.service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    assert sum(1 for item in context.observations.rows if item.state == "active") == 2
    context.service.register_extraction_version(
        kind="rule",
        key="balcon",
        version="balcon.rule-v2",
        payload={"rule": "balcon", "module": "umbral.application.criteria.rules"},
        correlation_id=uuid4(),
    )
    assert (
        sum(1 for item in context.observations.rows if item.state == "invalidated") == 2
    )
    assert sum(1 for item in context.observations.rows if item.state == "active") == 0


def test_invalidate_scope_concept_only_touches_that_concept() -> None:
    context = CriteriaTestContext()
    _seed_with_listings(context, ["con balcon y cocina separada"])
    context.service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    context.service.process_extraction(
        RecomputeScope("concept", "tipo_cocina"), job_execution_id=uuid4()
    )
    invalidated = context.service.invalidate_scope(RecomputeScope("concept", "balcon"))
    assert invalidated == 1
    states = {(item.concept_key, item.state) for item in context.observations.rows}
    assert ("balcon", "invalidated") in states
    assert ("tipo_cocina", "active") in states


def test_recompute_publishes_and_supersedes_invalidated() -> None:
    context = CriteriaTestContext()
    _seed_with_listings(context, ["con balcon", "sin balcon"])
    context.service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    context.service.register_extraction_version(
        kind="rule",
        key="balcon",
        version="balcon.rule-v2",
        payload={"rule": "balcon"},
        correlation_id=uuid4(),
    )
    summary = context.service.process_recompute(
        RecomputeScope("concept", "balcon"),
        cause="concept:balcon",
        job_execution_id=uuid4(),
    )
    assert summary["state"] == "succeeded"
    assert summary["superseded"] == 2
    assert summary["published"] == 2
    active = [item for item in context.observations.rows if item.state == "active"]
    assert len(active) == 2
    assert all(
        item.state == "superseded"
        for item in context.observations.rows
        if item.state != "active"
    )
    runs = context.recomputes.rows
    assert len(runs) == 1
    run_id = summary["recompute_run_id"]
    assert isinstance(run_id, str)
    run = runs[UUID(run_id)]
    assert run.state == "succeeded"
    assert run.counts["invalidated"] == 2
    event = next(
        item
        for item in context.events.events
        if item.event_type == "criteria.recompute_completed.v1"
    )
    assert event.payload["cause"] == "concept:balcon"
    assert event.payload["state"] == "succeeded"


def test_recompute_scope_parser_uses_normalizer_version() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    context.add_listing(description_text="con balcon", normalizer_version="silver-v2")
    context.add_listing(description_text="sin balcon", normalizer_version="silver-v1")
    summary = context.service.process_extraction(
        RecomputeScope("parser", "silver-v2"), job_execution_id=uuid4()
    )
    assert summary["published"] == 12
    listings = {item.listing_id for item in context.observations.rows}
    assert len(listings) == 1
