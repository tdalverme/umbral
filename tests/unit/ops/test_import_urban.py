"""US4 T035: the urban ops command fetches, hashes, uploads and triggers import.

The network, hashing, object-store upload and import trigger are all mocked so
the unit test runs without external services.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest import mock
from uuid import UUID, uuid4

from umbral.application.jobs.contracts import SubmitJob
from umbral.infrastructure.urban.osm_importer import ImportResult
from umbral.ops.urban import (
    fetch_snapshot,
    import_snapshot,
    rebuild_active_snapshot,
    sha256_of,
    upload_snapshot,
)


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self) -> list[bytes]:
        return [self._body]


class _FakeResponseCtx:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def __enter__(self) -> _FakeResponse:
        return self._response

    def __exit__(self, *args: object) -> None:
        return None


class _FakeClient:
    def __init__(self, body: bytes) -> None:
        self._response = _FakeResponse(body)
        self.requested_url: str | None = None

    def stream(self, method: str, url: str) -> _FakeResponseCtx:
        self.requested_url = url
        return _FakeResponseCtx(self._response)


class _FakeObjectStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def put_if_absent(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return "ref"


class _FakeSnapshotModel:
    def __init__(
        self, snapshot_id: UUID, source_path: str = "objects/urban/x.pbf"
    ) -> None:
        self.id = snapshot_id
        self.source_path = source_path


class _FakeSnapshots:
    def __init__(self) -> None:
        self.created: dict[str, object] = {}
        self.ready: list[tuple[object, dict[str, object]]] = []

    def create(self, **kwargs: object) -> _FakeSnapshotModel:
        snapshot_id = uuid4()
        self.created = kwargs
        return _FakeSnapshotModel(snapshot_id)

    def mark_ready(self, snapshot_id: UUID, **kwargs: object) -> _FakeSnapshotModel:
        self.ready.append((snapshot_id, kwargs))
        return _FakeSnapshotModel(snapshot_id)

    def active(self) -> _FakeSnapshotModel:
        return _FakeSnapshotModel(uuid4())

    def replace_snapshot_derived(
        self, snapshot_id: UUID, rows: object, **kwargs: object
    ) -> None:
        raise AssertionError("rebuild replacement was not expected in this fake")


class _FakeJobRuntime:
    def __init__(self) -> None:
        self.submitted: list[SubmitJob] = []

    def submit(self, command: SubmitJob) -> object:
        self.submitted.append(command)
        return "snapshot"


class _FakeRebuildSnapshots(_FakeSnapshots):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot = _FakeSnapshotModel(uuid4(), "objects/urban/current.pbf")
        self.replaced: dict[str, object] = {}

    def active(self) -> _FakeSnapshotModel:
        return self.snapshot

    def replace_snapshot_derived(
        self, snapshot_id: UUID, rows: object, **kwargs: object
    ) -> None:
        self.replaced = {
            "snapshot_id": snapshot_id,
            "rows": rows,
            **kwargs,
        }


class _FakeReadableObjectStore(_FakeObjectStore):
    def __init__(self) -> None:
        super().__init__()
        self.ref_keys: list[str] = []

    def ref_for_key(self, storage_key: str) -> str:
        self.ref_keys.append(storage_key)
        return "object-ref"

    def open(self, provider_ref: str) -> BytesIO:
        assert provider_ref == "object-ref"
        return BytesIO(b"stored pbf")


def test_sha256_of_computes_digest(tmp_path: Path) -> None:
    payload = tmp_path / "snapshot.osm.pbf"
    payload.write_bytes(b"hello urban")

    digest = sha256_of(payload)

    assert digest == "64dccf207a8a1b7fbd638be05bf2c956153173e216a4b8575158f73da108b5cb"


def test_fetch_snapshot_downloads_to_dest(tmp_path: Path) -> None:
    client = _FakeClient(b"binary pbf bytes")
    dest = tmp_path / "nested" / "argentina.osm.pbf"
    url = "https://download.geofabrik.de/south-america/argentina-latest.osm.pbf"

    fetch_snapshot(client, url=url, dest=dest)  # type: ignore[arg-type]

    assert dest.read_bytes() == b"binary pbf bytes"
    assert client.requested_url == url


def test_upload_snapshot_puts_with_sha_and_size(tmp_path: Path) -> None:
    source = tmp_path / "snapshot.osm.pbf"
    source.write_bytes(b"abc")
    store = _FakeObjectStore()

    digest = upload_snapshot(store, source=source, storage_key="objects/urban/x.pbf")

    assert digest == sha256_of(source)
    assert len(store.calls) == 1
    call = store.calls[0]
    assert call["storage_key"] == "objects/urban/x.pbf"
    assert call["sha256"] == digest
    assert call["size_bytes"] == 3
    assert call["content_type"] == "application/octet-stream"
    assert call["body"] is not None


def test_import_snapshot_marks_ready_and_triggers_batch() -> None:
    snapshots = _FakeSnapshots()
    runtime = _FakeJobRuntime()
    correlation_id = uuid4()

    with mock.patch(
        "umbral.ops.urban.osm_importer.import_snapshot", return_value=(3, 2)
    ) as importer:
        poi_count, linear_count, snapshot_id = import_snapshot(
            snapshots,
            session_factory=object(),
            source_path="objects/urban/x.pbf",
            source_hash="a" * 64,
            data_date=None,
            correlation_id=correlation_id,
            job_runtime=runtime,
            source_file="local/argentina.osm.pbf",
        )

    assert (poi_count, linear_count) == (3, 2)
    assert snapshots.created["source_path"] == "objects/urban/x.pbf"
    assert snapshots.created["source_hash"] == "a" * 64
    assert len(snapshots.ready) == 1
    assert snapshots.ready[0][0] == snapshot_id
    assert snapshots.ready[0][1]["poi_count"] == 3
    assert len(runtime.submitted) == 1
    command = runtime.submitted[0]
    assert command.identity.job_type == "urban.batch"
    assert command.correlation_id == correlation_id
    # osmitum parses the LOCAL file, not the object-store key: without this
    # the importer would try to open "objects/urban/x.pbf" on disk and crash.
    importer.assert_called_once()
    assert importer.call_args.kwargs["source_path"] == "local/argentina.osm.pbf"


def test_import_snapshot_falls_back_to_source_path_for_parsing() -> None:
    snapshots = _FakeSnapshots()
    runtime = _FakeJobRuntime()

    with mock.patch(
        "umbral.ops.urban.osm_importer.import_snapshot", return_value=(0, 0)
    ) as importer:
        import_snapshot(
            snapshots,
            session_factory=object(),
            source_path="local/argentina.osm.pbf",
            source_hash="b" * 64,
            data_date=None,
            correlation_id=uuid4(),
            job_runtime=runtime,
        )

    assert snapshots.created["source_path"] == "local/argentina.osm.pbf"
    assert importer.call_args.kwargs["source_path"] == "local/argentina.osm.pbf"


def test_rebuild_active_snapshot_reuses_object_store_and_submits_batch() -> None:
    snapshots = _FakeRebuildSnapshots()
    object_store = _FakeReadableObjectStore()
    runtime = _FakeJobRuntime()
    correlation_id = uuid4()
    staged = ImportResult(rows=(), poi_count=4, linear_count=5)

    with (
        mock.patch(
            "umbral.ops.urban.osm_importer.parse_snapshot", return_value=staged
        ) as parser,
        mock.patch(
            "umbral.ops.urban.SqlAlchemyObservationRepository"
        ) as observations,
    ):
        result = rebuild_active_snapshot(
            snapshots,
            object_store,
            session_factory=object(),
            job_runtime=runtime,
            correlation_id=correlation_id,
        )

    assert result == (4, 5, snapshots.snapshot.id)
    assert object_store.ref_keys == ["objects/urban/current.pbf"]
    parser.assert_called_once()
    source_path = Path(parser.call_args.kwargs["source_path"])
    assert source_path.name.endswith(".osm.pbf")
    assert snapshots.replaced["snapshot_id"] == snapshots.snapshot.id
    observations.return_value.invalidate_active_for_source.assert_called_once_with(
        "urban"
    )
    assert len(runtime.submitted) == 1
    assert str(snapshots.snapshot.id) in runtime.submitted[0].identity.idempotency_key
    assert str(correlation_id) in runtime.submitted[0].identity.idempotency_key
