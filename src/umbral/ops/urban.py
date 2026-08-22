"""Operator CLI for importing an OSM snapshot into urban categories.

Usage (same environment pattern as the other ops CLIs):
    python -m umbral.ops.urban --fetch --import

The command:
  1. downloads ``argentina-latest.osm.pbf`` from Geofabrik,
  2. computes its SHA-256,
  3. uploads it to object storage under ``objects/urban/<sha256>.osm.pbf``,
  4. parses it with the osmium importer into ``urban_categories``, marks the
     snapshot ready, and triggers the ``urban.batch`` recalculation job.

All steps are separable functions so the fetch/hash/upload/import can be
tested without network or a live Postgres/Redis (the test mocks them).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID, uuid4

import httpx

from umbral.application.jobs.contracts import SubmitJob
from umbral.infrastructure.db.repositories.criteria import (
    SqlAlchemyObservationRepository,
)
from umbral.infrastructure.db.repositories.urban import (
    SqlAlchemyUrbanSnapshotRepository,
)
from umbral.infrastructure.urban import osm_importer
from umbral.infrastructure.urban.contract_loader import load_urban_contract_published

_DEFAULT_URL = (
    "https://download.geofabrik.de/south-america/argentina-latest.osm.pbf"
)
_DEFAULT_DEST = str(
    Path(__file__).resolve().parents[3] / ".data" / "argentina-latest.osm.pbf"
)

SnapshotsLike = Any
ObjectStoreLike = Any
JobRuntimeLike = Any


def sha256_of(path: Path, chunk_size: int = 65536) -> str:
    """Compute the SHA-256 hex digest of a file without loading it whole."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def fetch_snapshot(client: httpx.Client, *, url: str, dest: Path) -> None:
    """Download the snapshot to ``dest``, failing loudly on non-200."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with client.stream("GET", url) as response:
        response.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)


def upload_snapshot(
    object_store: ObjectStoreLike, *, source: Path, storage_key: str
) -> str:
    """Upload ``source`` to object storage; returns the source SHA-256."""
    digest = sha256_of(source)
    size_bytes = source.stat().st_size
    with source.open("rb") as handle:
        object_store.put_if_absent(
            storage_key=storage_key,
            body=handle,
            sha256=digest,
            size_bytes=size_bytes,
            content_type="application/octet-stream",
        )
    return digest


def import_snapshot(
    snapshots: SnapshotsLike,
    *,
    session_factory: Any,
    source_path: str,
    source_hash: str,
    data_date: datetime | None,
    correlation_id: UUID,
    job_runtime: JobRuntimeLike,
    source_file: str | None = None,
) -> tuple[int, int, UUID]:
    """Parse the snapshot into categories, mark it ready and trigger the batch.

    Returns ``(poi_count, linear_count)`` of the imported category rows.

    ``source_path`` is the durable reference recorded on the snapshot (the
    object-store key); ``source_file`` is the local file osmium parses. When
    ``source_file`` is omitted the importer falls back to ``source_path``, so
    callers that hold the file locally can pass it directly.
    """
    contract = load_urban_contract_published()
    snapshot = snapshots.create(
        source_path=source_path,
        source_hash=source_hash,
        data_date=data_date,
        correlation_id=correlation_id,
    )
    poi_count, linear_count = osm_importer.import_snapshot(
        session_factory,
        snapshot_id=snapshot.id,
        source_path=source_file or source_path,
        contract=contract,
    )
    snapshots.mark_ready(
        snapshot.id,
        poi_count=poi_count,
        linear_count=linear_count,
        correlation_id=correlation_id,
    )
    job_runtime.submit(
        SubmitJob.create(
            job_type="urban.batch",
            logical_target="full",
            idempotency_key=f"urban.batch:{snapshot.id}",
            correlation_id=correlation_id,
        )
    )
    return poi_count, linear_count, snapshot.id


def rebuild_active_snapshot(
    snapshots: SnapshotsLike,
    object_store: ObjectStoreLike,
    *,
    session_factory: Any,
    job_runtime: JobRuntimeLike,
    correlation_id: UUID,
) -> tuple[int, int, UUID]:
    """Rebuild the active snapshot from its immutable object-store PBF."""
    snapshot = snapshots.active()
    if snapshot is None:
        raise RuntimeError("urban_snapshot_missing")

    contract = load_urban_contract_published()
    provider_ref = object_store.ref_for_key(snapshot.source_path)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".osm.pbf", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with object_store.open(provider_ref) as body:
                while chunk := body.read(1024 * 1024):
                    temporary.write(chunk)
            temporary.flush()

        staged = osm_importer.parse_snapshot(
            snapshot_id=snapshot.id,
            source_path=temporary_path,
            contract=contract,
        )
        SqlAlchemyObservationRepository(session_factory).invalidate_active_for_source(
            "urban"
        )
        snapshots.replace_snapshot_derived(
            snapshot.id,
            staged.rows,
            poi_count=staged.poi_count,
            linear_count=staged.linear_count,
            correlation_id=correlation_id,
        )
        job_runtime.submit(
            SubmitJob.create(
                job_type="urban.batch",
                logical_target="full",
                idempotency_key=f"urban.rebuild:{snapshot.id}:{correlation_id}",
                correlation_id=correlation_id,
            )
        )
        return staged.poi_count, staged.linear_count, snapshot.id
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _cli_import(
    session_factory: Any,
    object_store: ObjectStoreLike,
    job_runtime: JobRuntimeLike,
    *,
    dest: Path,
    source_hash: str,
    snapshot_prefix: str,
    date: datetime | None,
    correlation_id: UUID,
) -> tuple[int, int, UUID]:
    storage_key = f"{snapshot_prefix}/{source_hash}.osm.pbf"
    upload_snapshot(object_store, source=dest, storage_key=storage_key)
    snapshots = SqlAlchemyUrbanSnapshotRepository(session_factory)
    return import_snapshot(
        snapshots,
        session_factory=session_factory,
        source_path=storage_key,
        source_hash=source_hash,
        data_date=date,
        correlation_id=correlation_id,
        job_runtime=job_runtime,
        source_file=str(dest),
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from umbral.infrastructure.object_store.factory import build_object_store
    from umbral.workers.composition import build_process_dependencies

    deps = build_process_dependencies()
    object_store = build_object_store(deps.settings)
    correlation_id = uuid4()
    dest = Path(args.dest)

    if args.rebuild_active:
        poi_count, linear_count, snapshot_id = rebuild_active_snapshot(
            SqlAlchemyUrbanSnapshotRepository(deps.session_provider.session_factory),
            object_store,
            session_factory=deps.session_provider.session_factory,
            job_runtime=deps.runtime,
            correlation_id=correlation_id,
        )
        print(
            f"snapshot={snapshot_id} poi={poi_count} "
            f"linear={linear_count} rebuilt=true"
        )
        return 0

    if args.fetch:
        with httpx.Client(follow_redirects=True, timeout=600) as client:
            fetch_snapshot(client, url=args.url, dest=dest)

    source_hash = sha256_of(dest) if dest.exists() else None
    if args.import_:
        if source_hash is None:
            print(
                "error: snapshot file is missing; run with --fetch first",
                file=sys.stderr,
            )
            return 1
        date = datetime.fromisoformat(args.date) if args.date else None
        poi_count, linear_count, snapshot_id = _cli_import(
            deps.session_provider.session_factory,
            object_store,
            deps.runtime,
            dest=dest,
            source_hash=source_hash,
            snapshot_prefix=args.prefix,
            date=date,
            correlation_id=correlation_id,
        )
        print(
            f"snapshot={snapshot_id} poi={poi_count} "
            f"linear={linear_count} sha256={source_hash}"
        )
    else:
        print(f"sha256={source_hash} dest={dest}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m umbral.ops.urban",
        description="Import an OSM snapshot into urban categories.",
    )
    parser.add_argument("--fetch", action="store_true", help="download the snapshot")
    parser.add_argument(
        "--import",
        dest="import_",
        action="store_true",
        help="import categories and trigger the urban batch",
    )
    parser.add_argument(
        "--rebuild-active",
        action="store_true",
        help="rebuild the active snapshot from its stored PBF",
    )
    parser.add_argument("--url", default=_DEFAULT_URL, help="Geofabrik snapshot URL")
    parser.add_argument("--dest", default=_DEFAULT_DEST, help="local snapshot path")
    parser.add_argument(
        "--prefix", default="objects/urban", help="object storage prefix"
    )
    parser.add_argument("--date", default=None, help="snapshot data date (ISO-8601)")
    return parser


if __name__ == "__main__":
    sys.exit(main())
