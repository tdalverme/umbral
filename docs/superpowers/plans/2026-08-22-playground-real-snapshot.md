# Playground Real Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load a local JSON snapshot exported from Postgres/PostGIS so Geo Lab can browse real listings and inspect real urban evidence without a live product database connection.

**Architecture:** Add a catalog loader that combines the built-in demo fixture with an optional snapshot fixture. Keep the existing `PlaygroundFixture` interface and encode listing-specific urban data under `urban.by_listing`; only the local Geo inspector receives the optional catalog. Add a read-only SQLAlchemy exporter that writes the documented contract, then wire the snapshot path through the launcher and add a Geo Lab source selector.

**Tech Stack:** Python 3.13, SQLAlchemy 2, PostGIS/GeoAlchemy2, FastAPI, Next.js App Router, React, TypeScript, Vitest and pytest.

**Spec:** `docs/superpowers/specs/2026-08-22-playground-real-snapshot-design.md`

## Global Constraints

- The playground remains local-only and does not create or migrate product data.
- The exporter performs SELECT-only reads and writes only the requested local JSON output.
- Conversation Lab remains on the demo fixture; Geo Lab may select demo or real snapshot.
- The existing `UrbanSignalCalculator` remains the source of truth for signals.
- Real snapshot files live under `.data/`, which is ignored by git.
- Preserve unrelated generated-client modifications and `zonaprop-detail.html`.

---

### Task 1: Load optional snapshot catalog and listing-specific urban data

**Files:**
- Create: `src/umbral/infrastructure/playground/catalog.py`
- Modify: `src/umbral/infrastructure/playground/fixtures.py`
- Modify: `src/umbral/infrastructure/playground/geo.py`
- Test: `tests/unit/infrastructure/playground/test_catalog.py`
- Test: `tests/unit/infrastructure/playground/test_geo.py`

**Interfaces:**
- `load_playground_catalog(snapshot_path: Path | None = None) -> PlaygroundFixtures`
- `LocalGeoInspector(fixtures: PlaygroundFixtures | None = None)`
- `build_local_geo_inspector(snapshot_path: Path | None = None) -> LocalGeoInspector`

- [ ] **Step 1: Write failing loader and listing-specific geo tests.** Assert that a temporary snapshot is appended to the demo catalog, that a missing optional path leaves only demo, and that `urban.by_listing[listing_id]` is used for the selected listing.
- [ ] **Step 2: Run `pytest tests/unit/infrastructure/playground/test_catalog.py tests/unit/infrastructure/playground/test_geo.py -q` and verify the new imports/constructor behavior fail.**
- [ ] **Step 3: Implement catalog loading and `_urban_for_listing`.** Keep the current demo JSON contract valid; validate snapshot JSON through the existing required `id/profile/listings/urban` sections and reject malformed `by_listing` mappings.
- [ ] **Step 4: Run the focused tests and verify both demo and snapshot paths pass.**
- [ ] **Step 5: Commit `feat: load real playground snapshots`.**

### Task 2: Add the read-only PostGIS snapshot exporter

**Files:**
- Create: `src/umbral/infrastructure/playground/exporter.py`
- Create: `scripts/export-playground-snapshot.py`
- Test: `tests/unit/infrastructure/playground/test_exporter.py`

**Interfaces:**
- `export_playground_snapshot(session_factory, output_path: Path, listing_ids: Sequence[UUID] = (), limit: int = 50, radius_m: int = 5000, urban_snapshot_id: UUID | None = None) -> SnapshotExportSummary`
- `SnapshotExportSummary` reports output path, snapshot id, exported listing count, skipped listing count and feature count.

- [ ] **Step 1: Write failing pure serialization tests.** Feed fake listing/category rows and assert the output contains minimized listing fields, GeoJSON features, per-listing distance buckets and deterministic profile id; assert categories with no geometry are skipped.
- [ ] **Step 2: Run `pytest tests/unit/infrastructure/playground/test_exporter.py -q` and verify it fails because the exporter module is absent.**
- [ ] **Step 3: Implement the exporter.** Select the latest ready `UrbanSnapshot` unless `urban_snapshot_id` is supplied; select latest coordinate-bearing `SilverListing` rows, join `UrbanCategory` rows for the snapshot using `ST_Distance`/`ST_AsGeoJSON` on PostGIS geography, group by listing, and derive calculator buckets from actual distances. Use the active published urban contract version as metadata, omit descriptions/media, and never call `commit`.
- [ ] **Step 4: Add the CLI.** Support `--output`, repeated `--listing-id`, `--limit`, `--radius-m`, `--urban-snapshot-id` and `DATABASE_URL`; print a concise summary and fail with a clear message when PostGIS/database configuration is missing.
- [ ] **Step 5: Run unit tests and `python scripts/export-playground-snapshot.py --help`; verify the CLI has no import-time database side effect.**
- [ ] **Step 6: Commit `feat: export real playground snapshots`.**

### Task 3: Wire snapshot path into the local API and launcher

**Files:**
- Modify: `src/umbral/api/playground_main.py`
- Modify: `src/umbral/api/routers/playground.py`
- Modify: `scripts/playground.ps1`
- Modify: `tests/contract/test_playground_api.py`
- Modify: `tests/contract/test_playground_launcher.py`

**Interfaces:**
- `PLAYGROUND_SNAPSHOT_PATH` is an optional environment variable consumed only by `playground_main`.
- `GET /api/v1/playground/fixtures` returns demo plus the loaded snapshot summary when configured.

- [ ] **Step 1: Write failing API/launcher tests.** Assert `create_playground_app` uses a configured snapshot path, `/fixtures` returns both source ids/listings, and the launcher sets/prints `PLAYGROUND_SNAPSHOT_PATH` when `-SnapshotPath` is passed or `.data/playground/real-snapshot.json` exists.
- [ ] **Step 2: Run the focused contract tests and verify they fail.**
- [ ] **Step 3: Implement environment wiring.** Add an optional PowerShell `SnapshotPath`, validate it when explicitly provided, set the environment for the child API, and preserve demo-only fallback when absent. Pass the resolved path into `build_local_geo_inspector`; do not instantiate Postgres in the local API entrypoint.
- [ ] **Step 4: Run focused API and launcher tests plus PowerShell parsing.**
- [ ] **Step 5: Commit `feat: wire snapshot source into playground`.**

### Task 4: Add Geo Lab source and listing selection

**Files:**
- Modify: `apps/web/src/components/playground/playground-view.tsx`
- Modify: `apps/web/src/lib/playground/types.ts`
- Test: `apps/web/src/components/playground/playground-view.test.tsx`

**Interfaces:**
- `GeoLab` receives `fixtures: PlaygroundFixture[]` and selects one `fixture_id` before selecting a listing.
- The browser continues to call only `/api/playground/fixtures` and `/api/playground/geo`.

- [ ] **Step 1: Write failing UI tests.** Mock fixture loading with demo plus a real snapshot, assert the Geo Lab source selector shows both ids, selecting the snapshot shows its listings, and inspecting sends the selected `fixture_id` and listing id.
- [ ] **Step 2: Run `npm test --workspace @umbral/web -- src/components/playground/playground-view.test.tsx` and verify the new test fails.**
- [ ] **Step 3: Implement the source selector.** Keep Conversation Lab bound to the demo fixture, initialize Geo Lab to the first available source, reset listing/inspection when source changes, and show a clear “snapshot real” label based on the source id.
- [ ] **Step 4: Run the focused UI test, TypeScript and lint.**
- [ ] **Step 5: Commit `feat: browse real snapshot listings in geo lab`.**

### Task 5: Document export and verify the complete local flow

**Files:**
- Modify: `docs/runbooks/runtime-local.md`

- [ ] **Step 1: Document the no-DB demo flow and the real snapshot flow.** Include the `DATABASE_URL` export command, an example exporter invocation, `.data/playground/real-snapshot.json`, launcher `-SnapshotPath`, and the fact that the output is read-only and ignored by git.
- [ ] **Step 2: Run backend focused tests, web playground tests, typecheck, lint and `git diff --check`.**
- [ ] **Step 3: Start the launcher with a generated/test snapshot and verify `GET /playground`, `GET /api/playground/fixtures` and `POST /api/playground/geo` return successful responses for the real source.**
- [ ] **Step 4: Inspect status to ensure only feature files are staged and unrelated workspace changes remain untouched.**
- [ ] **Step 5: Commit `docs: document real playground snapshots`.**
