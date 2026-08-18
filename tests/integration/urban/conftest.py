"""Shared Postgres backend and urban-domain seeding for integration tests."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from geoalchemy2.elements import WKTElement
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tests.support.criteria import build_listing
from tests.support.silver import build_run

from umbral.application.ingestion.contracts import RawListingSnapshot
from umbral.infrastructure.db.models.urban import UrbanCategory
from umbral.infrastructure.db.repositories.criteria import (
    SqlAlchemyExtractionVersionRepository,
)
from umbral.infrastructure.db.repositories.imports import (
    SqlAlchemyImportRunRepository,
    SqlAlchemyRawSnapshotRepository,
)
from umbral.infrastructure.db.repositories.silver import (
    SqlAlchemyCanonicalPropertyRepository,
    SqlAlchemySilverListingRepository,
)
from umbral.infrastructure.db.repositories.urban import (
    SqlAlchemyNeighborhoodStatsRepository,
    SqlAlchemyUrbanContractRepository,
    SqlAlchemyUrbanPrimitiveRepository,
    SqlAlchemyUrbanSignalRepository,
    SqlAlchemyUrbanSnapshotRepository,
)

SessionFactory = Callable[[], Session]

_NOW = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def urban_backend(request: pytest.FixtureRequest) -> SessionFactory:
    """Postgres at head for one urban integration test."""
    connection = request.getfixturevalue("postgres_container")
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", connection.url)
    command.upgrade(config, "head")
    engine = create_engine(connection.url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def teardown() -> None:
        engine.dispose()

    request.addfinalizer(teardown)
    return factory


def seed_listing(
    factory: SessionFactory,
    *,
    geometry: tuple[float, float] | None = None,
    geo_precision: Literal[
        "exact", "block", "neighborhood", "approximate", "unknown"
    ] = "exact",
    neighborhood: str | None = "Caballito",
) -> UUID:
    """Insert one silver listing with precise coordinates (or neighborhood)."""
    run_repo = SqlAlchemyImportRunRepository(factory)
    import_run = run_repo.create(
        run_id=uuid4(),
        source=build_run(source_id="fixture").source,
        batch_key=f"urban-seed-{uuid4()}",
        file_format="json",
        file_name="urban-seed.json",
        file_sha256="0" * 64,
        file_size_bytes=0,
        raw_storage_key=f"objects/raw/{uuid4()}",
        job_execution_id=None,
        correlation_id=uuid4(),
        actor_kind="system",
        actor_id=None,
        now=_NOW,
    )
    snapshots = SqlAlchemyRawSnapshotRepository(factory)
    canonicals = SqlAlchemyCanonicalPropertyRepository(factory)
    listings = SqlAlchemySilverListingRepository(factory)
    canonical = canonicals.create(
        canonical_property_id=uuid4(),
        first_seen_at=_NOW,
        correlation_id=uuid4(),
        actor_kind="system",
        actor_id=None,
    )
    snapshot_id = uuid4()
    snapshots.insert(
        RawListingSnapshot(
            snapshot_id=snapshot_id,
            run_id=import_run.run_id,
            source=import_run.source,
            external_id=f"urban-listing-{uuid4()}",
            payload={},
            content_sha256=uuid4().hex,
            content_type="application/json",
            size_bytes=0,
            published_at=_NOW,
            captured_at=_NOW,
        )
    )
    listing = replace(
        build_listing(
            geo_precision=geo_precision,
            geometry=geometry,
        ),
        canonical_property_id=canonical.canonical_property_id,
        run_id=import_run.run_id,
        snapshot_id=snapshot_id,
        source=import_run.source,
        neighborhood=neighborhood,
    )
    listings.insert(listing)
    return listing.listing_id


def seed_urban_contract(
    factory: SessionFactory, *, correlation_id: UUID | None = None
) -> tuple[UUID, str]:
    """Register (superseding any active) and return (contract_version_id, version)."""
    from umbral.infrastructure.urban.contract_loader import (
        load_urban_contract_published,
    )

    contract = load_urban_contract_published()
    repo = SqlAlchemyUrbanContractRepository(factory)
    model = repo.register(
        contract_version=contract.contract_version,
        payload=_contract_payload(contract),
        correlation_id=correlation_id or uuid4(),
        now=_NOW,
    )
    return model.id, contract.contract_version


def _contract_payload(contract: object) -> dict[str, object]:
    from dataclasses import asdict

    return dict(asdict(cast(Any, contract)))


def seed_urban_snapshot(
    factory: SessionFactory,
    *,
    source_path: str = "objects/urban/argentina-latest.osm.pbf",
    source_hash: str | None = None,
    poi_count: int = 0,
    linear_count: int = 0,
) -> UUID:
    repo = SqlAlchemyUrbanSnapshotRepository(factory)
    model = repo.create(
        source_path=source_path,
        source_hash=source_hash,
        data_date=_NOW,
        correlation_id=uuid4(),
        now=_NOW,
    )
    repo.mark_ready(
        model.id, poi_count=poi_count, linear_count=linear_count, correlation_id=uuid4()
    )
    return model.id


def seed_urban_category(
    factory: SessionFactory,
    snapshot_id: UUID,
    *,
    category: str,
    osm_id: str,
    kind: str = "poi",
    lon: float = -58.4,
    lat: float = -34.6,
    name: str | None = None,
) -> None:
    with factory() as session:
        session.add(
            UrbanCategory(
                id=uuid4(),
                created_at=_NOW,
                updated_at=_NOW,
                actor_kind="service",
                actor_id=None,
                source="urban.test",
                correlation_id=uuid4(),
                snapshot_id=snapshot_id,
                osm_id=osm_id,
                category=category,
                kind=kind,
                name=name,
                tags={},
                geometry=WKTElement(f"SRID=4326;POINT({lon} {lat})"),
            )
        )
        session.commit()


def urban_repos(factory: SessionFactory) -> dict[str, Any]:
    return {
        "contracts": SqlAlchemyUrbanContractRepository(factory),
        "snapshots": SqlAlchemyUrbanSnapshotRepository(factory),
        "primitives": SqlAlchemyUrbanPrimitiveRepository(factory),
        "signals": SqlAlchemyUrbanSignalRepository(factory),
        "stats": SqlAlchemyNeighborhoodStatsRepository(factory),
        "extraction_versions": SqlAlchemyExtractionVersionRepository(factory),
    }


def run_urban_batch(
    factory: SessionFactory,
    *,
    correlation_id: UUID | None = None,
) -> object:
    """Run the real batch composition and persist the produced observations.

    The active contract is self-registered by the composition; an active ready
    snapshot must already exist (seed it with ``seed_urban_snapshot``).
    """
    from typing import cast

    from umbral.application.criteria.contracts import ListingObservation
    from umbral.infrastructure.db.repositories.criteria import (
        SqlAlchemyObservationRepository,
    )
    from umbral.infrastructure.urban.composition import build_urban_batch_service

    cid = correlation_id or uuid4()
    service = build_urban_batch_service(session_factory=factory, correlation_id=cid)
    outcome = service.run(correlation_id=cid)
    observations = outcome.observations
    if observations:
        repo = SqlAlchemyObservationRepository(factory)
        # Recompute replaces all urban observations; invalidate previous active
        # ones so the unique partial index does not clash.
        repo.invalidate_active_for_source("urban")
        repo.publish(
            cast(tuple[ListingObservation, ...], observations),
            supersede_ids=(),
            run=None,
            event=None,
        )
    return outcome


def observations_for_listing(
    factory: SessionFactory, listing_id: UUID
) -> tuple[Mapping[str, object], ...]:
    """Fetch persisted listing observations as plain mappings."""
    from sqlalchemy import select

    from umbral.infrastructure.db.models.criteria import (
        ListingObservation as ObservationModel,
    )

    with factory() as session:
        models = session.scalars(
            select(ObservationModel).where(
                ObservationModel.listing_id == listing_id
            )
        )
        return tuple(
            {
                "id": model.id,
                "listing_id": model.listing_id,
                "concept_key": model.concept_key,
                "matcher_type": model.matcher_type,
                "score": float(model.score),
                "confidence": float(model.confidence),
                "value": model.value,
                "state": model.state,
                "failure_code": model.failure_code,
                "source": model.source,
                "evidence": dict(model.evidence or {}),
                "extraction_version_id": model.extraction_version_id,
            }
            for model in models
        )
