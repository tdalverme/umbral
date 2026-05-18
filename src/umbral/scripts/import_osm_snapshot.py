"""Importa un snapshot OSM local a tablas PostGIS para scoring urbano.

Uso:
    python -m umbral.scripts.import_osm_snapshot path/to/caba.osm.pbf
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import structlog

from umbral.database import UrbanSignalRepository
from umbral.urban import classify_osm_linear_feature, classify_osm_poi

logger = structlog.get_logger()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _point_wkt(lon: float, lat: float) -> str:
    return f"SRID=4326;POINT({lon} {lat})"


def _line_wkt(nodes) -> str | None:
    coords = []
    for node in nodes:
        if not node.location.valid():
            continue
        coords.append(f"{node.lon} {node.lat}")
    if len(coords) < 2:
        return None
    return "SRID=4326;LINESTRING(" + ",".join(coords) + ")"


def import_snapshot(path: str, *, batch_size: int = 500) -> dict:
    try:
        import osmium
    except ImportError as exc:
        raise RuntimeError(
            "Falta instalar osmium. Ejecuta `pip install osmium` o instala requirements.txt."
        ) from exc

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(path)

    repo = UrbanSignalRepository()
    snapshot = repo.create_snapshot(source_path=str(source), source_hash=_hash_file(source))
    snapshot_id = snapshot["id"]

    stats = {"pois": 0, "linear": 0}
    poi_batch: list[dict] = []
    linear_batch: list[dict] = []

    def flush():
        nonlocal poi_batch, linear_batch
        if poi_batch:
            repo.upsert_pois(poi_batch)
            poi_batch = []
        if linear_batch:
            repo.upsert_linear_features(linear_batch)
            linear_batch = []

    class Handler(osmium.SimpleHandler):
        def node(self, node):
            tags = dict(node.tags)
            category = classify_osm_poi(tags)
            if not category or not node.location.valid():
                return
            poi_batch.append(
                {
                    "osm_snapshot_id": snapshot_id,
                    "osm_id": f"node/{node.id}",
                    "category": category,
                    "name": tags.get("name"),
                    "tags": tags,
                    "latitude": node.lat,
                    "longitude": node.lon,
                    "geom": _point_wkt(node.lon, node.lat),
                }
            )
            stats["pois"] += 1
            if len(poi_batch) >= batch_size:
                flush()

        def way(self, way):
            tags = dict(way.tags)
            category = classify_osm_linear_feature(tags)
            if not category:
                return
            geom = _line_wkt(way.nodes)
            if not geom:
                return
            linear_batch.append(
                {
                    "osm_snapshot_id": snapshot_id,
                    "osm_id": f"way/{way.id}",
                    "category": category,
                    "name": tags.get("name"),
                    "tags": tags,
                    "geom": geom,
                }
            )
            stats["linear"] += 1
            if len(linear_batch) >= batch_size:
                flush()

    logger.info("Importando snapshot OSM", path=str(source), snapshot_id=snapshot_id)
    Handler().apply_file(str(source), locations=True)
    flush()
    repo.mark_snapshot_ready(snapshot_id, poi_count=stats["pois"], linear_count=stats["linear"])
    logger.info("Snapshot OSM importado", **stats, snapshot_id=snapshot_id)
    return {"snapshot_id": snapshot_id, **stats}


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa POIs y features lineales desde un snapshot OSM local")
    parser.add_argument("path", help="Archivo .osm.pbf/.osm local")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    try:
        import_snapshot(args.path, batch_size=args.batch_size)
    except Exception as exc:
        logger.error("No se pudo importar snapshot OSM", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
