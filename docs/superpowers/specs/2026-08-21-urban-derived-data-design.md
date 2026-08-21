# Urban Derived Data: Consistency, Station Identity, and Line Geometry

**Status:** Design approved for planning

**Date:** 2026-08-21

## Goal

Make the Urban derived-data pipeline explainable and geometrically correct
without changing the existing scoring semantics: `transit_access` and
`rail_noise` continue to use nearest-distance primitives, while counts become
explicit factual evidence rather than ambiguous zero-filled fields.

## Context and findings

The active Urban contract declares the primitives consumed by each signal. The
current implementation computes distances from `urban_categories`, persists
`urban_primitives`, and calculates signals directly from the distance buckets.
The persisted primitive row, however, always initializes `count_300m` and
`count_600m` to zero even when the contract does not declare that metric.

For the investigated listing, OSM contains a subway station at roughly 105 m,
multiple subway entrances between roughly 92 m and 171 m, and Line D ways at
roughly 86 m. The observed values are therefore consistent with the source
data:

- `subway_station.count_600m = 8` counts one station plus entrances.
- `subway_station.count_300m = 0` is an unsupported metric, not an observed
  zero.
- `subway_line.count_300m = 0` and `count_600m = 0` are unsupported metrics;
  the valid `subway_line.nearest_m` is present.

The OSM importer currently stores a linear way as a point at its first node.
The existing `urban_categories` geometry column is also typed as `POINT`, so
the current snapshot cannot be repaired into real line geometry from database
rows alone. The PBF object referenced by the snapshot is already in object
storage and can be reused for a derived-data rebuild without downloading a new
OSM snapshot.

## Decisions

### Scoring semantics remain unchanged

No new weights or count terms are added to the scoring contract in this change.

- `transit_access` continues to use `bus_stop.count_300m`,
  `subway_station.nearest_m`, and `train_station.nearest_m`.
- `rail_noise` continues to use `railway.nearest_m` and
  `subway_line.nearest_m`.
- There is no new 800 m score term.

Counts at explicit radii are retained for factual evidence and future product
explanations, not silently introduced into ranking.

### Contract is the single source of truth for metric support

Every primitive reference in every signal formula must resolve to a declared
category and metric in the active Urban contract. A metric that is not declared
is not a measured zero. The persisted representation will use `NULL` for
unsupported count columns, while the contract/conformance layer remains the
authority for whether a metric is available.

### Subway stations are station objects, not entrances

The `subway_station` mapping will match subway station objects and exclude
`railway=subway_entrance`. The same station-only category will feed both
`nearest_m` and any station counts, so entrances cannot move either the factual
count or the proximity evidence.

Line ways remain individual OSM source objects for auditability. The current
scope does not add a line-count signal; if line counts are later added, they
must count distinct stable line identities such as `tags.ref`, not raw OSM way
segments.

### Linear features use their real geometry

`urban_categories.geometry` will accept point geometries for POIs and
`LINESTRING` geometries for linear features. The importer will construct a
line from all valid way nodes. PostGIS will calculate point-to-line distances
directly; no routing engine or road-network traversal is introduced.

### Rebuild the current snapshot from its stored PBF

The current snapshot identity, source hash, and object-store PBF remain the
lineage anchor. A rebuild operation will:

1. acquire a per-snapshot rebuild lock;
2. open the existing PBF through the object-store port;
3. parse the corrected station mapping and full way geometries into a staging
   set;
4. replace the snapshot's category rows atomically, preserving the existing
   snapshot id and source metadata;
5. clear and recompute snapshot-scoped primitives, signals, and neighborhood
   stats;
6. enqueue and execute `urban.batch`.

The rebuild is idempotent. Repeating it for the same snapshot produces one
category row per `(snapshot_id, osm_id, category)` and one derived row per
declared listing/category/metric identity.

## Persistence and lineage changes

The current `urban_signals` uniqueness and replacement operations are scoped by
contract but not by snapshot. The implementation will scope signal replacement
and reads to `(snapshot_id, contract_version_id)` and extend the unique key to
include `snapshot_id`. This keeps prior snapshot results auditable and prevents
the current rebuild from deleting signals belonging to another snapshot.

Snapshot-derived cleanup will be explicit and ordered:

1. urban observations for the active source are invalidated by the existing
   observation lifecycle;
2. snapshot-scoped signals and stats are removed;
3. snapshot-scoped primitives are removed;
4. category rows are replaced;
5. `urban.batch` writes the new derived rows and observations.

The operation must not delete the immutable `urban_snapshots` row or its raw
object. Failure before promotion leaves the previous derived set available;
failure after promotion marks the rebuild as failed and does not enqueue a
batch against a partial category set.

## Alternatives considered

### New external snapshot import

Rejected for this fix. It downloads a large PBF again, changes snapshot
lineage unnecessarily, and does not solve the need for a deterministic derived
rebuild operation.

### SQL-only patch of current points

Useful only for removing existing subway entrances. It cannot recover the
missing vertices of line ways, so it cannot produce real line geometry.

### Keep the old point representation and approximate lines

Rejected. It preserves the current systematic distance error and makes future
line-count or explanation features unreliable.

## Verification strategy

The implementation plan must add tests at these seams:

- Contract conformance: every signal primitive reference resolves to a declared
  primitive metric; unsupported metrics are not emitted as measured zeros.
- Primitive derivation: declared counts are computed; undeclared count fields
  remain `None`.
- Subway classification: a station plus any number of entrances produces one
  `subway_station` source category.
- OSM way import: a multi-node way becomes a `LINESTRING`; repeated import for
  one snapshot does not duplicate `(snapshot_id, osm_id, category)`.
- PostGIS distance: a listing near the middle of a line uses the nearest point
  on the line, not the way's first node.
- Snapshot rebuild integration: existing PBF is reused, old category/derived
  rows are replaced, signal lineage remains snapshot-scoped, and a second
  rebuild is idempotent.
- Regression: the investigated listing has one station-level object,
  `subway_station.nearest_m` near the station node, and
  `subway_line.nearest_m` near the real line geometry while the existing score
  terms remain unchanged.

## Operational acceptance

After deployment:

1. apply the geometry/nullable-metric/snapshot-scope migration;
2. run the new active-snapshot rebuild command against the existing object;
3. run `urban.batch` and wait for the worker;
4. verify no duplicate category keys, no entrance categories contributing to
   `subway_station`, `LINESTRING` geometry for linear rows, and non-null
   `nearest_m` for Line D;
5. verify `transit_access` and `rail_noise` result shapes and formulas are
   unchanged.

## Non-goals

- changing score weights or adding an 800 m score term;
- calculating walking/network travel times;
- counting line ways as distinct subway lines;
- downloading a new OSM snapshot for this correction;
- redesigning the API or the general Urban contract beyond metric/geometry
  consistency needed by this fix.
