"""Seed a local dev database with a user, a session and Silver listings.

The API must run with ``umbral.api.dev_main:app`` (durable runtime, SQLAlchemy
identity). Prints the session cookie value to paste in the browser devtools.

Usage:

    $env:DATABASE_URL = "postgresql+psycopg://umbral:local@127.0.0.1/umbral"
    .venv\Scripts\python.exe scripts\seed-local.py
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from umbral.application.ingestion.contracts import RawListingSnapshot, SourceIdentity
from umbral.application.ingestion.import_contract import validate_record
from umbral.application.silver.silver_schema import normalize_snapshot
from umbral.domain.identity.models import (
    MagicLinkAttempt,
    MagicLinkRequest,
    ProductSession,
    ProductUser,
    RoleAssignment,
)
from umbral.infrastructure.db.repositories.identity import SqlAlchemyIdentityStore
from umbral.infrastructure.db.repositories.imports import (
    SqlAlchemyImportRunRepository,
    SqlAlchemyRawSnapshotRepository,
)
from umbral.infrastructure.db.repositories.silver import (
    SqlAlchemyCanonicalPropertyRepository,
    SqlAlchemySilverListingRepository,
)
from umbral.infrastructure.ingestion.contract_loader import load_contract_v2
from umbral.infrastructure.silver.contract_loader import load_silver_schema

NOW = datetime.now(timezone.utc)
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://umbral:local@127.0.0.1/umbral")


def main() -> None:
    engine = create_engine(DATABASE_URL)
    factory = sessionmaker(engine, expire_on_commit=False)

    store = SqlAlchemyIdentityStore(
        factory, fingerprint_key=b"local-dev-fingerprint-key", environment="preview"
    )
    user_id = uuid4()
    token = secrets.token_urlsafe(32)
    request_id = uuid4()
    attempt_id = uuid4()
    with store.transaction():
        existing = store.user_for_email("demo@example.invalid")
        if existing is not None:
            user_id = existing.id
        else:
            store.save_user(
                ProductUser(
                    id=user_id,
                    normalized_email="demo@example.invalid",
                    status="active",
                )
            )
        if store.active_role(user_id, "user") is None:
            store.save_role(
                RoleAssignment(
                    id=uuid4(),
                    product_user_id=user_id,
                    role="user",
                    granted_at=NOW,
                )
            )
        store.save_request(
            MagicLinkRequest(
                id=request_id,
                email_fingerprint=hashlib.sha256(b"demo@example.invalid").digest(),
                origin_fingerprint=hashlib.sha256(b"local").digest(),
                decision="proceed",
                requested_at=NOW,
                purge_after=datetime(2099, 1, 1, tzinfo=timezone.utc),
                correlation_id=uuid4(),
            )
        )
        store.save_attempt(
            MagicLinkAttempt(
                id=attempt_id,
                request_id=request_id,
                subject_kind="product_user",
                invitation_id=None,
                product_user_id=user_id,
                state="issued",
                issued_at=NOW,
                expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            )
        )
        store.save_session(
            ProductSession(
                id=uuid4(),
                product_user_id=user_id,
                magic_link_attempt_id=attempt_id,
                token_digest=hashlib.sha256(token.encode()).digest(),
                last_activity_at=NOW,
            )
        )

    _seed_silver(factory)
    _seed_urban_signals(factory)
    _seed_soft(factory)

    print()
    print("Sesi��n local creada. Cookie para pegar en el navegador (devtools -> Application -> Cookies):")
    print()
    print(f"  umbral_local_session={token}")
    print()
    print("Usuario: demo@example.invalid (rol user, sin magic link)")


_SOFT_QUALITATIVE_DEFAULTS = {
    "luminosidad": {
        "value": "media",
        "evidence": "descripcion de demo con buena luz",
        "confidence": 0.8,
    },
    "estado_general": {
        "value": "bueno",
        "evidence": "descripcion de demo en buen estado",
        "confidence": 0.8,
    },
}


def _build_local_criteria(factory):
    """Criteria service for the seed: managed provider when configured,
    otherwise the deterministic fake with qualitative defaults."""
    from umbral.infrastructure.criteria.composition import build_criteria_service
    from umbral.infrastructure.criteria.extractors.fake import FakeStructuredExtractor

    provider = "fake"
    managed_api_key = None
    managed_model = None
    try:
        from umbral.infrastructure.config.settings import Settings

        settings = Settings()
        provider = settings.extraction_provider
        managed_api_key = settings.extraction_managed_api_key
        managed_model = settings.extraction_managed_model
    except Exception:  # noqa: BLE001 - seed falls back to fake
        pass
    if provider == "managed" and managed_api_key:
        return build_criteria_service(
            session_factory=factory,
            job_runtime=None,
            extraction_provider="managed",
            extraction_endpoint=None,
            extraction_api_key=managed_api_key,
            extraction_model=managed_model,
            qualitative_max_attempts=2,
            batch_size=250,
            urban_context_enabled=True,
        )
    return build_criteria_service(
        session_factory=factory,
        job_runtime=None,
        extraction_provider="fake",
        extractor=FakeStructuredExtractor(dict(_SOFT_QUALITATIVE_DEFAULTS)),
        urban_context_enabled=True,
    )


_URBAN_SIGNALS_DEMO = [
    # Palermo (9f024c31) y Belgrano/Recoleta: cafes y transporte cerca.
    {"listing_external": "demo-1", "signal_type": "cafe", "geometry": "POINT(-58.4245 -34.5833)", "algorithm_version": "v1"},
    {"listing_external": "demo-1", "signal_type": "cafe", "geometry": "POINT(-58.4240 -34.5831)", "algorithm_version": "v1"},
    {"listing_external": "demo-1", "signal_type": "transport", "geometry": "POINT(-58.4242 -34.5835)", "algorithm_version": "v1"},
    {"listing_external": "demo-2", "signal_type": "cafe", "geometry": "POINT(-58.4260 -34.5850)", "algorithm_version": "v1"},
    {"listing_external": "demo-2", "signal_type": "transport", "geometry": "POINT(-58.4262 -34.5852)", "algorithm_version": "v1"},
    {"listing_external": "demo-3", "signal_type": "transport", "geometry": "POINT(-58.3915 -34.5935)", "algorithm_version": "v1"},
]


def _seed_urban_signals(factory) -> None:
    """Seed demo urban signals (cafe/transport) near the demo listings."""
    from sqlalchemy import text

    from umbral.infrastructure.db.repositories.criteria import (
        SqlAlchemyUrbanSignalRepository,
    )

    with factory() as session:
        session.execute(
            text("DELETE FROM urban_signals WHERE signal_source = 'osm-demo'")
        )
        session.commit()
    repo = SqlAlchemyUrbanSignalRepository(factory)
    with factory() as session:
        rows = session.execute(
            text(
                "SELECT external_id, id FROM silver_listings "
                "WHERE source_id = 'demo-source'"
            )
        ).all()
    by_external = {str(row[0]): str(row[1]) for row in rows}
    now = datetime.now(timezone.utc)
    inserted = 0
    for raw in _URBAN_SIGNALS_DEMO:
        listing_id = by_external.get(raw["listing_external"])
        if listing_id is None:
            continue
        repo.insert(
            {
                "signal_id": uuid4(),
                "created_at": now,
                "correlation_id": uuid4(),
                "listing_id": UUID(listing_id),
                "signal_type": raw["signal_type"],
                "signal_source": "osm-demo",
                "observed_at": now,
                "geometry": raw["geometry"],
                "algorithm_version": raw["algorithm_version"],
                "payload": {"source": "demo"},
            }
        )
        inserted += 1
    print(f"Seed Urban: {inserted} senales demo (re-sembradas, sin duplicados).")


def _seed_soft(factory, criteria=None) -> None:
    """Seed concepts + extraction versions and publish observations (idempotent).

    The extraction runs inline (no job runtime): rules always publish; the
    qualitative concepts publish when the extractor responds and stay ``failed``
    with code otherwise, never breaking the seed.
    """
    from umbral.application.criteria.contracts import RecomputeScope

    criteria = criteria or _build_local_criteria(factory)
    correlation_id = uuid4()
    registered = criteria.seed_registry(correlation_id)
    summary = criteria.process_extraction(
        RecomputeScope("full", None),
        job_execution_id=uuid4(),
        correlation_id=correlation_id,
    )
    print(
        "Seed Criteria: "
        f"{registered} conceptos registrados (0 si ya existian); "
        f"extraccion -> {dict(summary)}"
    )


def _seed_silver(factory) -> None:
    run_repo = SqlAlchemyImportRunRepository(factory)
    snapshots = SqlAlchemyRawSnapshotRepository(factory)
    canonicals = SqlAlchemyCanonicalPropertyRepository(factory)
    listings = SqlAlchemySilverListingRepository(factory)

    if listings.latest_for_source("demo-source", "demo-1") is not None:
        print("Seed Silver: ya existe, se omite (no duplica listings).")
        return

    run = run_repo.create(
        run_id=uuid4(),
        source=SourceIdentity("demo-source", "v1", "2"),
        batch_key=f"demo-seed-{uuid4().hex[:8]}",
        file_format="json",
        file_name="demo-seed.json",
        file_sha256="0" * 64,
        file_size_bytes=0,
        raw_storage_key=f"objects/raw/{uuid4()}",
        job_execution_id=None,
        correlation_id=uuid4(),
        actor_kind="system",
        actor_id=None,
        now=NOW,
    )
    contract = load_contract_v2()
    schema = load_silver_schema()

    sample = [
        {"external_id": "demo-1", "neighborhood": "Palermo", "price": 650000, "expenses": 45000, "currency": "ARS", "rooms": 2, "surface_m2": 48, "latitude": -34.5833, "longitude": -58.4245, "address_text": "Av. Santa Fe 3000", "property_type": "apartment", "operation": "rental"},
        {"external_id": "demo-2", "neighborhood": "Palermo", "price": 820000, "expenses": 60000, "currency": "ARS", "rooms": 3, "surface_m2": 70, "latitude": -34.5850, "longitude": -58.4260, "address_text": "Thames 1500", "property_type": "apartment", "operation": "rental"},
        {"external_id": "demo-3", "neighborhood": "Recoleta", "price": 550000, "expenses": 35000, "currency": "ARS", "rooms": 1, "surface_m2": 35, "latitude": -34.5935, "longitude": -58.3915, "address_text": "Junin 1000", "property_type": "apartment", "operation": "rental"},
        {"external_id": "demo-4", "neighborhood": "Recoleta", "price": 950000, "expenses": 80000, "currency": "ARS", "rooms": 3, "surface_m2": 85, "latitude": -34.5950, "longitude": -58.3920, "address_text": "Libertador 1500", "property_type": "apartment", "operation": "rental"},
        {"external_id": "demo-5", "neighborhood": "Palermo", "price": 720000, "expenses": 50000, "currency": "ARS", "rooms": 2, "surface_m2": 55, "address_text": "", "property_type": "apartment", "operation": "rental"},
        {"external_id": "demo-6", "neighborhood": "Belgrano", "price": 1100000, "expenses": 90000, "currency": "ARS", "rooms": 4, "surface_m2": 95, "latitude": -34.5625, "longitude": -58.4590, "address_text": "Cabildo 2000", "property_type": "apartment", "operation": "rental"},
    ]

    for payload in sample:
        result = validate_record(payload, contract)
        if not result.valid:
            continue
        snapshot = RawListingSnapshot(
            snapshot_id=uuid4(),
            run_id=run.run_id,
            source=run.source,
            external_id=str(payload["external_id"]),
            payload=payload,
            content_sha256=hashlib.sha256(
                str(payload).encode()
            ).hexdigest(),
            content_type="application/json",
            size_bytes=0,
            published_at=NOW,
            captured_at=NOW,
        )
        snapshots.insert(snapshot)
        fields = normalize_snapshot(snapshot, schema)
        canonical = canonicals.create(
            canonical_property_id=uuid4(),
            first_seen_at=NOW,
            correlation_id=uuid4(),
            actor_kind="system",
            actor_id=None,
        )
        from umbral.application.silver.contracts import NormalizedListing

        listings.insert(
            NormalizedListing(
                listing_id=uuid4(),
                canonical_property_id=canonical.canonical_property_id,
                run_id=run.run_id,
                snapshot_id=snapshot.snapshot_id,
                source=run.source,
                external_id=snapshot.external_id,
                url=None,
                published_at=NOW,
                last_observed_at=NOW,
                normalizer_version=schema.normalizer_version,
                operation=fields.operation,
                property_type=fields.property_type,
                price_value=fields.price_value,
                price_currency=fields.price_currency,
                expenses_value=fields.expenses_value,
                expenses_currency=fields.expenses_currency,
                total_cost=fields.total_cost,
                price_assumptions=fields.price_assumptions,
                surface_m2=fields.surface_m2,
                rooms=fields.rooms,
                bedrooms=fields.bedrooms,
                floor=fields.floor,
                amenities=fields.amenities,
                description_text=fields.description_text,
                location_text=fields.location_text,
                neighborhood=fields.neighborhood,
                geo_precision=fields.geo_precision,
                geometry=fields.geometry,
                geo_source=fields.geo_source,
                normalization_errors=fields.normalization_errors,
            )
        )
    print(f"Seed Silver: {len(sample)} listings insertados (barrios Palermo/Recoleta/Belgrano).")


if __name__ == "__main__":
    main()
