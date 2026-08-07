"""Integration: lineage walk observation -> extraction version -> listing -> Bronze."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from tests.integration.criteria.conftest import (
    build_criteria_service,
    seed_silver_listings,
)

from umbral.application.criteria.contracts import RecomputeScope
from umbral.infrastructure.db.models.criteria import (
    ExtractionVersion as ExtractionVersionModel,
)
from umbral.infrastructure.db.models.criteria import (
    ListingObservation as ObservationModel,
)
from umbral.infrastructure.db.models.silver import SilverListing as SilverListingModel


def test_lineage_walk_covers_every_observation(criteria_backend: Any) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=3)
    service = build_criteria_service(factory)
    service.seed_registry(correlation_id=uuid4())
    service.process_extraction(RecomputeScope("full", None), job_execution_id=uuid4())

    with factory() as session:
        observations = list(session.execute(select(ObservationModel)).scalars())
        assert len(observations) == 3 * 6
        for observation in observations:
            assert observation.extraction_version_id is not None
            version = session.get(
                ExtractionVersionModel, observation.extraction_version_id
            )
            assert version is not None
            assert version.kind in {"rule", "model"}
            listing = session.get(SilverListingModel, observation.listing_id)
            assert listing is not None
            assert listing.normalizer_version
            assert listing.snapshot_id is not None


def test_invalidated_observations_are_never_active(criteria_backend: Any) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=1)
    service = build_criteria_service(factory)
    service.seed_registry(correlation_id=uuid4())
    service.process_extraction(
        RecomputeScope("concept", "balcon"), job_execution_id=uuid4()
    )
    service.invalidate_scope(RecomputeScope("concept", "balcon"))
    with factory() as session:
        active = list(
            session.execute(
                select(ObservationModel).where(
                    ObservationModel.concept_key == "balcon",
                    ObservationModel.state == "active",
                )
            ).scalars()
        )
        assert active == []
