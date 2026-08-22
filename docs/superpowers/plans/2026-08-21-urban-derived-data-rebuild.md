# Urban Derived Data Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Urban primitives explainable, count subway stations once, calculate distances to real OSM line geometry, and reprocess the existing stored PBF without downloading a new snapshot.

**Architecture:** Keep the declarative Urban contract as the authority for supported primitive metrics and validate signal operators against those metrics. Parse OSM into a staged in-memory category set, then replace one snapshot's categories and derived rows in a single SQL transaction; the existing `urban.batch` worker recalculates primitives, signals, stats, and observations afterward. Preserve score formulas and snapshot lineage while changing signal replacement to the `(snapshot, contract)` scope.

**Tech Stack:** Python 3.13, Pydantic/dataclasses, SQLAlchemy 2, Alembic, GeoAlchemy2/PostGIS, osmium, pytest, filesystem/S3-compatible object storage, existing job runtime.

**Spec:** `docs/superpowers/specs/2026-08-21-urban-derived-data-design.md`

**Status:** Implemented and verified in commit `1e4ef7b`.

## Global Constraints

- `transit_access` continues to use `bus_stop.count_300m`, `subway_station.nearest_m`, and `train_station.nearest_m`.
- `rail_noise` continues to use `railway.nearest_m` and `subway_line.nearest_m`.
- Counts at explicit radii are evidence and are not added as new score terms.
- `subway_station` excludes `railway=subway_entrance`.
- Linear features are stored as `LINESTRING` geometries; no routing or walking-distance engine is added.
- The existing snapshot id, source hash, source path, and raw object remain unchanged during rebuild.
- Unsupported primitive count fields persist as `NULL`, never as measured zero.
- Snapshot-derived rows are unique by their existing identity keys and rebuilds are idempotent.
- Do not commit or modify the pre-existing untracked `zonaprop-detail.html`.

---

### Task 1: Enforce Urban contract and primitive metric consistency

**Files:**
- Modify: `contracts/urban/v2/urban-contract-v2.json`
- Modify: `src/umbral/application/urban/contract.py`
- Modify: `src/umbral/application/urban/primitives.py`
- Modify: `src/umbral/infrastructure/db/models/urban.py`
- Modify: `src/umbral/infrastructure/db/repositories/urban.py`
- Modify: `src/umbral/application/urban/ports.py`
- Modify: `tests/fakes/urban.py`
- Create: `tests/unit/application/urban/test_primitives.py`
- Modify: `tests/contract/test_urban_contract.py`
- Modify: `tests/integration/urban/test_repository.py`

**Interfaces:**
- Consumes: `UrbanContract`, `PrimitiveSpec`, `buckets_to_primitives()`, and the existing primitive repository port.
- Produces: nullable `count_300m`/`count_600m` repository values and contract validation that rejects operator/metric mismatches.

- [ ] **Step 1: Write the failing contract and primitive tests.**

Add tests asserting that the published v2 station mapping contains only `station=subway`; a `count` signal term cannot reference `nearest_m`; a `distance` term cannot reference `count_600m`; and a `subway_line` primitive produced from a nearest-only contract has `None` for both count fields. Add a repository integration assertion that a nullable count remains `None` after insert/read.

```python
def test_unsupported_primitive_counts_are_not_measured_as_zero() -> None:
    contract = load_urban_contract(CONTRACT_V2_PATH)
    rows = buckets_to_primitives(
        listing_id=uuid4(),
        snapshot_id=uuid4(),
        buckets={"subway_line": {"nearest_m": [85.0]}},
        contract=contract,
    )
    row = next(row for row in rows if row["category"] == "subway_line")
    assert row["count_300m"] is None
    assert row["count_600m"] is None
    assert row["nearest_m"] == 85.0
```

- [ ] **Step 2: Run the focused tests and verify they fail.**

Run: `pytest tests/unit/application/urban/test_primitives.py tests/contract/test_urban_contract.py -q`

Expected: failure because the current primitive builder emits zero and the current v2 mapping includes `railway=subway_entrance`; the operator/metric mismatch cases must also fail before implementation.

- [ ] **Step 3: Implement contract validation and nullable primitive derivation.**

Change v2 `subway_station` mapping to `[["station", "subway"]]`. In `_parse_terms()`, require `op == "count"` only for `PrimitiveSpec(kind="count")` and `op == "distance"` only for `PrimitiveSpec(kind="nearest")`; raise `UrbanContractInvalid` with the signal and primitive reference when incompatible. Keep the existing reference validation and score formulas unchanged.

In `buckets_to_primitives()`, initialize both count keys to `None` and overwrite only metrics declared by the category spec. Change `UrbanPrimitive.count_300m` and `.count_600m` to `Mapped[int | None]` and change the SQL repository/fake conversion to preserve `None` instead of calling the zero default helper.

- [ ] **Step 4: Run the focused tests and repository regression.**

Run: `pytest tests/unit/application/urban/test_primitives.py tests/contract/test_urban_contract.py tests/integration/urban/test_repository.py -q`

Expected: PASS, with all v2 score terms still resolving to declared primitive metrics and unsupported fields read as `None`.

- [ ] **Step 5: Commit the contract/primitive slice.**

```bash
git add contracts/urban/v2/urban-contract-v2.json src/umbral/application/urban/contract.py src/umbral/application/urban/primitives.py src/umbral/infrastructure/db/models/urban.py src/umbral/infrastructure/db/repositories/urban.py src/umbral/application/urban/ports.py tests/fakes/urban.py tests/unit/application/urban/test_primitives.py tests/contract/test_urban_contract.py tests/integration/urban/test_repository.py
git commit -m "fix: make urban primitive metrics explicit"
```

### Task 2: Migrate Urban geometry and signal lineage keys

**Files:**
- Create: `alembic/versions/0021_urban_derived_consistency.py`
- Modify: `src/umbral/infrastructure/db/models/urban.py`
- Modify: `tests/migrations/test_0021_urban_derived_consistency.py`

**Interfaces:**
- Consumes: the existing 0017 Urban tables and current v2 primitive category sets.
- Produces: a generic SRID-4326 geometry column, nullable count columns, and unique signal identity `(listing_id, snapshot_id, contract_version_id, signal)`.

- [ ] **Step 1: Write the migration test.**

Create a migration test that upgrades to `0021_urban_derived_consistency` and asserts:

```sql
SELECT type FROM geometry_columns
WHERE f_table_name = 'urban_categories' AND f_geometry_column = 'geometry'
```

returns `GEOMETRY`; `information_schema.columns.is_nullable` is `YES` for both primitive count columns; and `pg_constraint` contains a unique constraint over `listing_id`, `snapshot_id`, `contract_version_id`, and `signal`, but not the previous three-column identity.

- [ ] **Step 2: Run the migration test and verify it fails.**

Run: `pytest tests/migrations/test_0021_urban_derived_consistency.py -q`

Expected: failure because the repository has no 0021 revision and the schema still declares a POINT geometry, non-null counts, and a contract-only signal uniqueness key.

- [ ] **Step 3: Implement the Alembic migration.**

Create revision `0021_urban_derived_consistency` with down revision `0020_silver_listing_attributes`.

1. Alter `urban_categories.geometry` to `geometry(GEOMETRY,4326)` using the existing values.
2. Alter `urban_primitives.count_300m` and `count_600m` to nullable and remove their server defaults.
3. Backfill old unsupported values to `NULL` using the v2 declared sets: `count_300m` is supported only by `supermarket`, `convenience`, `pharmacy`, `health`, `cafe`, `nightlife`, `restaurant`, `bus_stop`, and `gym`; `count_600m` is supported by those categories plus `subway_station`, `green_space`, `school`, `cinema`, `library`, `theatre`, and `bicycle_parking`. Set the corresponding column to `NULL` for every other category.
4. Drop `uq_urban_signals_listing_contract_signal` and create `uq_urban_signals_listing_snapshot_contract_signal` over `listing_id`, `snapshot_id`, `contract_version_id`, `signal`.
5. Replace the `ix_urban_signals_listing_contract` index with the same name over `listing_id`, `snapshot_id`, and `contract_version_id`.

The downgrade must refuse when Urban data exists, matching 0017's data-loss policy; otherwise restore the prior geometry subtype, non-null defaults, unique key, and index.

- [ ] **Step 4: Align SQLAlchemy metadata and run migration tests.**

Use `Geometry(geometry_type="GEOMETRY", srid=4326)` for `UrbanCategory.geometry`, nullable integer mappings for primitive counts, and the four-column signal `UniqueConstraint`/three-column signal index. Run:

`pytest tests/migrations/test_0017_urban_signals.py tests/migrations/test_0021_urban_derived_consistency.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the schema slice.**

```bash
git add alembic/versions/0021_urban_derived_consistency.py src/umbral/infrastructure/db/models/urban.py tests/migrations/test_0021_urban_derived_consistency.py
git commit -m "feat: support urban line geometry and snapshot signal lineage"
```

### Task 3: Import station objects and real OSM line geometry

**Files:**
- Modify: `src/umbral/infrastructure/urban/osm_importer.py`
- Modify: `tests/unit/infrastructure/urban/test_osm_importer.py`
- Modify: `tests/integration/urban/conftest.py`
- Modify: `tests/integration/urban/test_geometry.py`

**Interfaces:**
- Consumes: v2 `TagMapping` sets and osmium node/way callbacks.
- Produces: point POIs, `LINESTRING` linear categories from all valid way nodes, and one category row per `(snapshot_id, osm_id, category)`.

- [ ] **Step 1: Write failing importer tests.**

Expose a small pure helper for geometry construction and test it without osmium:

```python
def test_way_geometry_uses_all_valid_nodes() -> None:
    geometry = linestring_wkt([( -58.40, -34.60), (-58.41, -34.61), (-58.42, -34.62)])
    assert geometry == "SRID=4326;LINESTRING(-58.4 -34.6,-58.41 -34.61,-58.42 -34.62)"
```

Add a classification test using the published v2 mapping that `{"station": "subway"}` maps to `subway_station` and `{"railway": "subway_entrance"}` does not. Add a PostGIS integration test that seeds a listing near the middle of a three-node line and asserts the distance calculator returns the point-to-line distance, not the distance to the first node. Add a uniqueness assertion after replacing/importing the same snapshot twice.

- [ ] **Step 2: Run importer and geometry tests and verify they fail.**

Run: `pytest tests/unit/infrastructure/urban/test_osm_importer.py tests/integration/urban/test_geometry.py -q`

Expected: failure because the importer has no line WKT helper, the contract still matches entrances, and `way()` currently persists the first node as a POINT.

- [ ] **Step 3: Implement pure point/line geometry builders and update `_RowCollector`.**

Add `point_wkt(lon, lat)` and `linestring_wkt(points)` helpers. `linestring_wkt()` must reject fewer than two valid points and serialize all coordinates in input order. Change `_RowCollector.add()` to accept a `WKTElement` geometry rather than separate longitude/latitude arguments, keeping audit fields and counts unchanged.

- [ ] **Step 4: Update osmium node/way callbacks.**

Keep node POIs as POINT geometries. For ways, classify tags before reading nodes, collect every valid node location, require at least two points, and persist `WKTElement(linestring_wkt(points))`. Keep the way's stable `w<id>` `osm_id` and all tags. The existing unique database key remains the duplication guard; do not merge line segments by name or `ref` because individual OSM ways are the auditable source objects.

- [ ] **Step 5: Run unit and PostGIS geometry tests.**

Run: `pytest tests/unit/infrastructure/urban/test_osm_importer.py tests/integration/urban/test_geometry.py -q`

Expected: PASS; the nearest distance for a listing adjacent to the middle segment is materially closer than the distance to the first node.

- [ ] **Step 6: Commit the importer slice.**

```bash
git add src/umbral/infrastructure/urban/osm_importer.py tests/unit/infrastructure/urban/test_osm_importer.py tests/integration/urban/conftest.py tests/integration/urban/test_geometry.py
git commit -m "fix: import urban ways as real line geometry"
```

### Task 4: Make batch signal replacement snapshot-scoped

**Files:**
- Modify: `src/umbral/application/urban/ports.py`
- Modify: `src/umbral/application/urban/batch.py`
- Modify: `src/umbral/infrastructure/db/repositories/urban.py`
- Modify: `tests/fakes/urban.py`
- Modify: `tests/unit/application/urban/test_batch.py`
- Modify: `tests/integration/urban/test_repository.py`
- Modify: `tests/integration/urban/test_reimport.py`

**Interfaces:**
- Consumes: `snapshot_id` and `contract_version_id` resolved by `UrbanBatchService.run()`.
- Produces: `replace_for_snapshot_contract(snapshot_id, contract_version_id, rows)` and `for_listing_snapshot_contract(listing_id, snapshot_id, contract_version_id)`.

- [ ] **Step 1: Write the failing lineage tests.**

Seed two snapshots and one contract, write one signal for each snapshot, replace only the first snapshot, and assert the second remains. Update batch assertions to read by the active snapshot. Change the reimport expectation so the old snapshot's signals remain queryable and the new snapshot has its own rows.

```python
signals.replace_for_snapshot_contract(old_snapshot, contract_id, old_rows)
signals.replace_for_snapshot_contract(new_snapshot, contract_id, new_rows)
assert signals.for_listing_snapshot_contract(listing_id, old_snapshot, contract_id)
assert signals.for_listing_snapshot_contract(listing_id, new_snapshot, contract_id)
```

- [ ] **Step 2: Run the focused lineage tests and verify they fail.**

Run: `pytest tests/unit/application/urban/test_batch.py tests/integration/urban/test_repository.py tests/integration/urban/test_reimport.py -q`

Expected: failure because the current port/repository deletes all rows for a contract and reads without a snapshot argument.

- [ ] **Step 3: Implement the new port and repository methods.**

Change the protocol, fake, and SQLAlchemy repository to delete only rows matching both snapshot and contract, insert the current rows, and filter reads by all three identities. Change `UrbanBatchService` to call the new replacement method with the active snapshot id. Keep stats replacement snapshot-scoped as it already is.

- [ ] **Step 4: Run Urban unit/integration tests.**

Run: `pytest tests/unit/application/urban/test_batch.py tests/integration/urban/test_repository.py tests/integration/urban/test_reimport.py -q`

Expected: PASS with previous snapshot signal rows preserved and score calculation unchanged.

- [ ] **Step 5: Commit the lineage slice.**

```bash
git add src/umbral/application/urban/ports.py src/umbral/application/urban/batch.py src/umbral/infrastructure/db/repositories/urban.py tests/fakes/urban.py tests/unit/application/urban/test_batch.py tests/integration/urban/test_repository.py tests/integration/urban/test_reimport.py
git commit -m "fix: scope urban signal replacement by snapshot"
```

### Task 5: Add atomic active-snapshot rebuild from object storage

**Files:**
- Modify: `src/umbral/infrastructure/db/repositories/urban.py`
- Modify: `src/umbral/application/urban/ports.py`
- Modify: `src/umbral/ops/urban.py`
- Modify: `tests/unit/ops/test_import_urban.py`
- Create: `tests/integration/urban/test_rebuild.py`
- Modify: `tests/integration/urban/conftest.py`

**Interfaces:**
- Consumes: `UrbanSnapshot.source_path`, `ObjectStore.ref_for_key()`, `ObjectStore.open()`, the staged importer result, and `SubmitJob`.
- Produces: `rebuild_active_snapshot(...)` and CLI flag `python -m umbral.ops.urban --rebuild-active`.

- [ ] **Step 1: Write failing rebuild tests.**

Unit-test that the rebuild resolves the active snapshot's object-store key, copies the opened PBF to a temporary local file, parses that file, and submits an `urban.batch` job with an idempotency key containing the snapshot id and rebuild correlation id. Assert it does not call `fetch_snapshot()` or create a new snapshot.

Integration-test the SQL replacement contract with seeded categories, primitives, signals, and stats: after rebuild, the old category/derived rows for the snapshot are gone, staged rows are present once, the `urban_snapshots` row and source path are unchanged, and a second rebuild produces the same counts and no duplicate `(snapshot_id, osm_id, category)` keys.

- [ ] **Step 2: Run rebuild tests and verify they fail.**

Run: `pytest tests/unit/ops/test_import_urban.py tests/integration/urban/test_rebuild.py -q`

Expected: failure because no active rebuild function, atomic replacement repository method, or CLI flag exists.

- [ ] **Step 3: Add an atomic snapshot replacement repository method.**

Implement `replace_snapshot_derived(snapshot_id, rows, poi_count, linear_count, correlation_id)` in the SQLAlchemy snapshot repository. In one session transaction, delete snapshot-scoped `NeighborhoodSignalStats`, `UrbanSignal`, `UrbanPrimitive`, and `UrbanCategory` rows; add the staged `UrbanCategory` rows; update the existing snapshot's counts, correlation id, and timestamp; commit only after all inserts succeed. The method must not delete the snapshot row or its source metadata. A parse or database exception propagates and no batch job is submitted.

- [ ] **Step 4: Implement object-store staging and active rebuild.**

Add `rebuild_active_snapshot()` in `umbral.ops.urban`:

1. Read `snapshots.active()` and fail with `urban_snapshot_missing` if absent.
2. Resolve `snapshot.source_path` with `object_store.ref_for_key()` and copy `object_store.open(ref)` to a `NamedTemporaryFile` in chunks.
3. Parse the local PBF into staged rows using the published contract; parsing must finish before any database deletion.
4. Invalidate active Urban observations through `SqlAlchemyObservationRepository.invalidate_active_for_source("urban")`.
5. Call the atomic repository replacement method.
6. Submit `urban.batch` with `logical_target="full"` and idempotency key `urban.rebuild:{snapshot_id}:{correlation_id}`.

Extend `main()` and `build_parser()` with `--rebuild-active`. Make `--rebuild-active` independent of `--fetch`/`--import`; it never downloads or creates a snapshot. Keep the existing import flow unchanged except for the corrected importer.

- [ ] **Step 5: Run unit, integration, and CLI parser tests.**

Run: `pytest tests/unit/ops/test_import_urban.py tests/integration/urban/test_rebuild.py tests/integration/urban/test_batch_worker.py -q`

Expected: PASS; repeated rebuilds retain one snapshot, one category identity per source object, and one derived set for the active snapshot.

- [ ] **Step 6: Commit the rebuild slice.**

```bash
git add src/umbral/infrastructure/db/repositories/urban.py src/umbral/application/urban/ports.py src/umbral/ops/urban.py tests/unit/ops/test_import_urban.py tests/integration/urban/test_rebuild.py tests/integration/urban/conftest.py
git commit -m "feat: rebuild urban snapshot from stored pbf"
```

### Task 6: Run full verification and document Railway operation

**Files:**
- Modify: `docs/ops/urban-signals.md`
- Modify: `tests/integration/urban/test_batch_worker.py`
- Modify: `tests/integration/urban/test_lineage.py`
- Modify: `tests/integration/urban/test_observations.py`

**Interfaces:**
- Consumes: the migration, importer, batch, and rebuild command from Tasks 1–5.
- Produces: an operational runbook and regression evidence for the affected listing behavior.

- [ ] **Step 1: Add the regression assertions.**

Use the existing PostGIS fixture to assert that station counts are based on station objects, line nearest distance uses the line geometry, unsupported primitive counts are `NULL`, and `transit_access`/`rail_noise` still expose the same formula terms. Do not introduce an 800 m score input.

- [ ] **Step 2: Update the Urban runbook.**

Document the deployment order:

```text
alembic upgrade head
python -m umbral.ops.urban --rebuild-active
```

Explain that `--rebuild-active` reuses `UrbanSnapshot.source_path` from object storage, does not download Geofabrik, leaves the snapshot id/hash unchanged, and enqueues the worker batch after the atomic category replacement. Include SQL checks for duplicate category keys, `ST_GeometryType()` of linear rows, subway entrance exclusion, and non-null Line D nearest distance.

- [ ] **Step 3: Run the complete verification suite.**

Run:

```bash
pytest tests/unit/application/urban tests/unit/infrastructure/urban tests/unit/ops/test_import_urban.py tests/contract/test_urban_contract.py tests/migrations/test_0017_urban_signals.py tests/migrations/test_0021_urban_derived_consistency.py tests/integration/urban -q
```

Then run the repository harness: `./scripts/check.ps1`.

Expected: both commands exit 0. If the integration Postgres fixture is unavailable, report that exact external dependency failure separately and still run all unit/contract/migration tests that do not require it.

- [ ] **Step 4: Review the plan against the approved design.**

Verify that every design decision has a corresponding implementation or test: nullable unsupported metrics, station-only mapping, real line geometry, idempotent replacement, snapshot-scoped signals, preservation of snapshot/raw object, no score change, and operational rebuild from the stored PBF.

- [ ] **Step 5: Commit documentation and final verification.**

```bash
git add docs/ops/urban-signals.md tests/integration/urban/test_batch_worker.py tests/integration/urban/test_lineage.py tests/integration/urban/test_observations.py
git commit -m "docs: add urban snapshot rebuild runbook"
```
