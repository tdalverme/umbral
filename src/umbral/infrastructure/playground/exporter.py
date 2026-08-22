"""Read-only exporter for real listings and urban geometry snapshots."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session

from umbral.infrastructure.urban.contract_loader import load_urban_contract_published

SessionFactory = Callable[[], Session]


@dataclass(frozen=True, slots=True)
class SnapshotExportSummary:
    output_path: Path
    snapshot_id: str
    listing_count: int
    skipped_listing_count: int
    feature_count: int


def build_snapshot_payload(
    *,
    listings: Sequence[Mapping[str, object]],
    features: Sequence[Mapping[str, object]],
    urban_snapshot_id: str,
    contract_version: str,
) -> dict[str, Any]:
    """Build the JSON contract consumed by the no-database playground."""

    listing_payloads = [_serialize_listing(item) for item in listings]
    by_listing: dict[str, dict[str, Any]] = {
        str(item["id"]): {
            "snapshot_id": urban_snapshot_id,
            "contract_version": contract_version,
            "features": [],
            "poi_distances": {},
            "linear_distances": {},
        }
        for item in listing_payloads
    }

    feature_count = 0
    for raw_feature in features:
        listing_id = str(raw_feature.get("listing_id", ""))
        urban = by_listing.get(listing_id)
        if urban is None:
            continue
        distance = float(raw_feature.get("distance_m", 0.0))
        category = str(raw_feature.get("category", ""))
        kind = str(raw_feature.get("kind", "poi"))
        feature_id = f"{raw_feature.get('osm_id', '')}:{category}"
        geometry = _parse_geometry(raw_feature.get("geometry"))
        if geometry is None:
            continue
        urban["features"].append(
            {
                "id": feature_id,
                "name": str(raw_feature.get("name") or category),
                "category": category,
                "kind": kind,
                "distance_m": distance,
                "geometry": geometry,
            }
        )
        distance_buckets = urban[
            "linear_distances" if kind == "linear" else "poi_distances"
        ]
        metrics = distance_buckets.setdefault(
            category,
            {"count_300m": [], "count_600m": [], "nearest_m": []},
        )
        if distance <= 300:
            metrics["count_300m"].append(distance)
        if distance <= 600:
            metrics["count_600m"].append(distance)
        metrics["nearest_m"].append(distance)
        feature_count += 1

    profile_id = str(uuid5(NAMESPACE_URL, f"umbral-playground:{urban_snapshot_id}"))
    return {
        "id": f"real-snapshot-{urban_snapshot_id}",
        "profile": {
            "id": profile_id,
            "name": f"Real snapshot {urban_snapshot_id}",
            "operation": "rental",
            "zones": [],
            "status": "active",
            "version": 1,
        },
        "listings": listing_payloads,
        "urban": {
            "snapshot_id": urban_snapshot_id,
            "contract_version": contract_version,
            "by_listing": by_listing,
        },
        "meta": {
            "source": "postgres-postgis",
            "feature_count": feature_count,
        },
    }


def export_playground_snapshot(
    session_factory: SessionFactory,
    output_path: Path,
    *,
    listing_ids: Sequence[UUID] = (),
    limit: int = 50,
    radius_m: int = 5000,
    urban_snapshot_id: UUID | None = None,
) -> SnapshotExportSummary:
    """Export a bounded, read-only slice from the current PostGIS database."""

    if limit < 1:
        raise ValueError("limit must be positive")
    if radius_m < 1:
        raise ValueError("radius_m must be positive")

    listing_filter, listing_params = _listing_filter(listing_ids)
    with session_factory() as session:
        snapshot = _ready_snapshot(session, urban_snapshot_id)
        if snapshot is None:
            raise ValueError("no hay un urban snapshot ready para exportar")
        snapshot_id = str(snapshot["id"])

        listing_rows = list(
            session.execute(
                text(
                    f"""
                    SELECT
                        sl.id::text AS listing_id,
                        sl.source_id,
                        sl.external_id,
                        sl.url,
                        sl.neighborhood,
                        ST_Y(sl.geometry) AS latitude,
                        ST_X(sl.geometry) AS longitude,
                        sl.geo_precision,
                        sl.total_cost,
                        sl.price_value,
                        sl.price_currency,
                        sl.expenses_value,
                        sl.surface_m2,
                        sl.rooms,
                        sl.bedrooms,
                        sl.floor,
                        sl.property_type,
                        sl.amenities
                    FROM silver_listings sl
                    WHERE sl.geometry IS NOT NULL
                      {listing_filter}
                    ORDER BY sl.captured_at DESC, sl.id
                    LIMIT :listing_limit
                    """
                ),
                {**listing_params, "listing_limit": limit},
            ).mappings()
        )
        selected_ids = [str(row["listing_id"]) for row in listing_rows]
        if selected_ids:
            feature_rows = list(
                session.execute(
                    text(
                        f"""
                        SELECT
                            sl.id::text AS listing_id,
                            uc.osm_id,
                            uc.category,
                            uc.kind,
                            uc.name,
                            ST_Distance(
                                sl.geometry::geography,
                                uc.geometry::geography
                            ) AS distance_m,
                            ST_AsGeoJSON(uc.geometry) AS geometry
                        FROM silver_listings sl
                        JOIN urban_categories uc
                          ON uc.snapshot_id = :urban_snapshot_id
                        WHERE sl.geometry IS NOT NULL
                          AND uc.geometry IS NOT NULL
                          AND sl.id IN ({_sql_placeholders(selected_ids)})
                          AND ST_DWithin(
                              sl.geometry::geography,
                              uc.geometry::geography,
                              :radius_m
                          )
                        ORDER BY sl.id, distance_m, uc.category, uc.osm_id
                        """
                    ),
                    {
                        "urban_snapshot_id": snapshot["id"],
                        "radius_m": radius_m,
                        **{
                            f"selected_listing_{index}": UUID(listing_id)
                            for index, listing_id in enumerate(selected_ids)
                        },
                    },
                ).mappings()
            )
        else:
            feature_rows = []

    contract_version = load_urban_contract_published().contract_version
    payload = build_snapshot_payload(
        listings=listing_rows,
        features=feature_rows,
        urban_snapshot_id=snapshot_id,
        contract_version=contract_version,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return SnapshotExportSummary(
        output_path=output_path,
        snapshot_id=snapshot_id,
        listing_count=len(listing_rows),
        skipped_listing_count=(
            max(0, len(set(listing_ids)) - len(selected_ids)) if listing_ids else 0
        ),
        feature_count=len(feature_rows),
    )


def _ready_snapshot(
    session: Session, snapshot_id: UUID | None
) -> Mapping[str, object] | None:
    if snapshot_id is not None:
        statement = text(
            "SELECT id FROM urban_snapshots "
            "WHERE id = :snapshot_id AND status = 'ready'"
        )
        return (
            session.execute(statement, {"snapshot_id": snapshot_id})
            .mappings()
            .first()
        )
    statement = text(
        "SELECT id FROM urban_snapshots "
        "WHERE status = 'ready' ORDER BY created_at DESC LIMIT 1"
    )
    return session.execute(statement).mappings().first()


def _listing_filter(listing_ids: Sequence[UUID]) -> tuple[str, dict[str, UUID]]:
    if not listing_ids:
        return "", {}
    placeholders = _sql_placeholders(
        [str(item) for item in listing_ids], prefix="listing_id"
    )
    return f"AND sl.id IN ({placeholders})", {
        f"listing_id_{index}": listing_id
        for index, listing_id in enumerate(listing_ids)
    }


def _sql_placeholders(
    values: Sequence[str], *, prefix: str = "selected_listing"
) -> str:
    return ", ".join(f":{prefix}_{index}" for index, _ in enumerate(values))


def _serialize_listing(row: Mapping[str, object]) -> dict[str, Any]:
    listing_id = str(row.get("listing_id", row.get("id", "")))
    if not listing_id:
        raise ValueError("listing row is missing listing_id")
    return {
        "id": listing_id,
        "uuid": listing_id,
        "source_id": _json_value(row.get("source_id")),
        "external_id": _json_value(row.get("external_id")),
        "url": _json_value(row.get("url")),
        "neighborhood": _json_value(row.get("neighborhood")),
        "latitude": _json_value(row.get("latitude")),
        "longitude": _json_value(row.get("longitude")),
        "geo_precision": _json_value(row.get("geo_precision")),
        "total_cost": _json_value(row.get("total_cost")),
        "price_value": _json_value(row.get("price_value")),
        "price_currency": _json_value(row.get("price_currency")),
        "expenses_value": _json_value(row.get("expenses_value")),
        "surface_m2": _json_value(row.get("surface_m2")),
        "rooms": _json_value(row.get("rooms")),
        "bedrooms": _json_value(row.get("bedrooms")),
        "floor": _json_value(row.get("floor")),
        "property_type": _json_value(row.get("property_type")),
        "amenities": _json_value(row.get("amenities") or []),
    }


def _parse_geometry(value: object) -> object:
    if isinstance(value, str):
        return json.loads(value)
    return value


def _json_value(value: object) -> Any:
    if isinstance(value, (Decimal, UUID)):
        return float(value) if isinstance(value, Decimal) else str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value
