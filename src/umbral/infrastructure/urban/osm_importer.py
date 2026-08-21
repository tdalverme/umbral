"""osmium-based importer that turns an OSM pbf into urban categories.

The importer lazily imports ``osmium`` so the rest of the application keeps
working when the optional system library is not installed; a clear error is
raised only when an import is actually attempted without it.

The classification is deliberately pure and exposed as :func:`classify` so it
can be unit-tested against small tag dicts without a real planet file.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from geoalchemy2.elements import WKTElement

from umbral.application.urban.contract import TagMapping, UrbanContract
from umbral.infrastructure.db.models.urban import UrbanCategory

OSM_POI_PREFIX = "n"
OSM_LINEAR_PREFIX = "w"

Classifier = Callable[[Mapping[str, str]], str | None]


class OsmiumUnavailable(RuntimeError):
    """osmium (and its native build) is not installed in this environment."""


def classify(tags: Mapping[str, str], mappings: Sequence[TagMapping]) -> str | None:
    """Return the first category whose osm_tags match ``tags``, else None.

    A category matches when any of its ``(key, value)`` tag pairs is present
    on the element (matching the "any tag" semantics of the contract).
    """
    for mapping in mappings:
        for key, value in mapping.osm_tags:
            if tags.get(key) == value:
                return mapping.category
    return None


@dataclass(slots=True)
class _RowCollector:
    rows: list[UrbanCategory] = field(default_factory=list)
    poi_count: int = 0
    linear_count: int = 0
    _now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add(
        self,
        *,
        snapshot_id: UUID,
        osm_id: str,
        category: str,
        kind: str,
        lon: float,
        lat: float,
        name: str | None,
        tags: Mapping[str, str],
    ) -> None:
        self.rows.append(
            UrbanCategory(
                id=uuid4(),
                created_at=self._now,
                updated_at=self._now,
                actor_kind="service",
                actor_id=None,
                source="urban.osm",
                correlation_id=uuid4(),
                snapshot_id=snapshot_id,
                osm_id=osm_id,
                category=category,
                kind=kind,
                name=name,
                tags=dict(tags),
                geometry=WKTElement(f"SRID=4326;POINT({lon} {lat})"),
            )
        )
        if kind == "poi":
            self.poi_count += 1
        else:
            self.linear_count += 1


def import_snapshot(
    session_factory: Callable[[], Any],
    *,
    snapshot_id: UUID,
    source_path: str | Path,
    contract: UrbanContract,
) -> tuple[int, int]:
    """Parse an ``.osm.pbf`` and persist classified urban categories.

    Returns ``(poi_count, linear_count)`` after committing the parsed rows.
    """
    try:  # pragma: no cover - exercised only when osmium is installed
        osmium = importlib.import_module("osmium")
    except ImportError as error:  # pragma: no cover
        raise OsmiumUnavailable(
            "osmium is not installed; run `pip install osmium` to import OSM pbf"
        ) from error

    writer = _RowCollector()
    poi = _classifier(contract.tags_mapping)
    linear = _classifier(contract.linear_tags_mapping)

    class _Handler(osmium.SimpleHandler):  # type: ignore
        def node(self, node: Any) -> None:  # pragma: no cover
            category = poi(_tags(node.tags))
            if category is None or not node.location.valid():
                return
            writer.add(
                snapshot_id=snapshot_id,
                osm_id=f"{OSM_POI_PREFIX}{node.id}",
                category=category,
                kind="poi",
                lon=node.location.lon,
                lat=node.location.lat,
                name=node.tags.get("name"),
                tags=_tags(node.tags),
            )

        def way(self, way: Any) -> None:  # pragma: no cover
            if len(way.nodes) < 2:
                return
            category = linear(_tags(way.tags))
            location = way.nodes[0].location
            if category is None or location is None or not location.valid():
                return
            writer.add(
                snapshot_id=snapshot_id,
                osm_id=f"{OSM_LINEAR_PREFIX}{way.id}",
                category=category,
                kind="linear",
                lon=location.lon,
                lat=location.lat,
                name=way.tags.get("name"),
                tags=_tags(way.tags),
            )

    handler = _Handler()
    handler.apply_file(str(source_path), locations=True)

    with session_factory() as session:
        for row in writer.rows:
            session.add(row)
        session.commit()
    return writer.poi_count, writer.linear_count


def _classifier(mappings: Sequence[TagMapping]) -> Classifier:
    def apply(tags: Mapping[str, str]) -> str | None:
        return classify(tags, mappings)

    return apply


def _tags(raw: object) -> dict[str, str]:
    if isinstance(raw, Mapping):
        return {str(key): str(value) for key, value in raw.items()}
    if not isinstance(raw, Iterable):
        return {}
    items = cast(Iterable[tuple[object, object]], raw)
    try:
        return {str(key): str(value) for key, value in items}
    except (TypeError, ValueError):
        return {}
