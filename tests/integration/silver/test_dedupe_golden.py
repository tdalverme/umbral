"""Golden dedupe pairs on the real backend: exact vs ambiguous (US2)."""

from __future__ import annotations

from tests.integration.silver.conftest import (
    SilverBackend,
    import_batch,
    normalize_service,
)


def test_deterministic_and_proposal_links_on_real_backend(
    silver_backend: SilverBackend,
) -> None:
    factory, object_store = silver_backend
    service = normalize_service(factory)

    run_a = import_batch(
        factory,
        object_store,
        name="dedupe-batch-a.json",
        source_id="source-a",
        batch_key="dedupe-a",
    )
    service.process(run_a.run_id)

    run_b = import_batch(
        factory,
        object_store,
        name="dedupe-batch-b.json",
        source_id="source-b",
        batch_key="dedupe-b",
    )
    summary = service.process(run_b.run_id)
    assert summary.listings_inserted == 2

    confirmed = service.links_by_state("confirmed")
    pending = service.links_by_state("pending")
    assert len(confirmed) >= 1
    assert len(pending) >= 1

    deterministic = [link for link in confirmed if link.method == "deterministic"]
    assert deterministic
    link = deterministic[0]
    assert link.fingerprint is not None
    assert "fingerprint" in link.evidence

    a = service.listings.get(link.listing_a_id)
    b = service.listings.get(link.listing_b_id)
    assert a is not None and b is not None
    assert a.canonical_property_id == b.canonical_property_id
    assert len(service.canonical_listings(a.canonical_property_id)) == 2

    # Ambiguous pairs stay pending and never auto-merge into one canonical.
    for proposal in pending:
        assert proposal.method == "proposal"
        assert proposal.score is not None and proposal.score >= 0.6
        la = service.listings.get(proposal.listing_a_id)
        lb = service.listings.get(proposal.listing_b_id)
        assert la is not None and lb is not None
        assert la.canonical_property_id != lb.canonical_property_id


def test_proposal_transitions_are_persisted(silver_backend: SilverBackend) -> None:
    factory, object_store = silver_backend
    service = normalize_service(factory)
    run_a = import_batch(
        factory,
        object_store,
        name="dedupe-batch-a.json",
        source_id="source-a",
        batch_key="t-a",
    )
    service.process(run_a.run_id)
    run_b = import_batch(
        factory,
        object_store,
        name="dedupe-batch-b.json",
        source_id="source-b",
        batch_key="t-b",
    )
    service.process(run_b.run_id)

    pending = service.links_by_state("pending")
    assert len(pending) >= 1
    for proposal in pending:
        confirmed = service.confirm_link(proposal.link_id, actor_id="operator-1")
        assert confirmed.state == "confirmed"
        assert confirmed.decided_by == "operator-1"
        reloaded = service.links.get(proposal.link_id)
        assert reloaded is not None and reloaded.state == "confirmed"

    assert service.links_by_state("pending") == ()
