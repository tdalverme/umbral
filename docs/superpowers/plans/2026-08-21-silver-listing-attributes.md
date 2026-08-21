# Silver Listing Attributes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the active import/Silver contracts with a clean-cut v2 that preserves structured listing attributes and source evidence from fresh ingestions.

**Architecture:** Bronze remains the immutable source payload. Silver v2 normalizes explicit listing facts into typed columns and keeps qualitative evidence in amenities/description; Criteria derives versioned observations from that evidence. Existing Silver v1 rows are excluded from active reads, with no backfill or v1 runtime support; historical Silver access remains available to normalization and lineage operations.

**Tech Stack:** Python 3.13, SQLAlchemy 2, Alembic, PostgreSQL/PostGIS, JSON contracts, pytest, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-21-silver-listing-attributes-design.md`

## Global Constraints

- Active import contract is version `2`; runtime rejects version `1`.
- Active Silver contract is version `2`; normalizer version is exactly `silver-schema-v2`.
- Missing values remain null/empty; invalid values produce bounded errors and are not invented.
- Qualitative booleans are criteria observations with evidence, not duplicate Silver columns.
- Existing unrelated working-tree changes must be preserved.
- Every production behavior change follows a failing test first.

---

### Task 1: Cut over the import and Silver contract documents

**Files:**
- Create: `contracts/import/v2/import-contract.json`
- Create: `contracts/silver/v2/silver-schema.json`
- Create: `contracts/silver/v2/silver-schema.md`
- Modify: `src/umbral/application/ingestion/import_contract.py`
- Modify: `src/umbral/application/ingestion/contracts.py`
- Modify: `src/umbral/infrastructure/ingestion/contract_loader.py`
- Modify: `src/umbral/application/silver/silver_schema.py`
- Modify: `src/umbral/infrastructure/silver/contract_loader.py`
- Test: `tests/contract/test_import_contract.py`
- Test: `tests/contract/test_silver_schema.py`

**Interfaces:**
- `parse_contract` and `normalize_contract_version` accept only `2`.
- `load_contract_v2()` loads `contracts/import/v2/import-contract.json`.
- `load_silver_schema()` loads `contracts/silver/v2/silver-schema.json`.
- `parse_silver_schema` accepts only contract document version `2`.

- [x] **Step 1: Write failing contract tests** asserting v2 versions, new fields, and rejection of v1.
- [x] **Step 2: Run `pytest tests/contract/test_import_contract.py tests/contract/test_silver_schema.py -q` and confirm failure caused by the missing v2 contract/loader behavior.**
- [x] **Step 3: Add v2 contract documents with `title`, `surface_covered_m2`, `bathrooms`, `toilettes`, `parking_spaces`, `age_years`, `disposition`, `orientation`, and the existing media fields.**
- [x] **Step 4: Change the parsers/loaders and `SourceIdentity` to accept only version 2.**
- [x] **Step 5: Run the focused contract tests and update import fixtures to declare version 2.**

### Task 2: Extend Zonaprop detail extraction

**Files:**
- Modify: `src/umbral/ops/import_zonaprop.py`
- Test: `tests/unit/ops/test_import_zonaprop.py`

**Interfaces:**
- Extend `Detail` with `title`, `surface_covered_m2`, `bathrooms`, `toilettes`, `parking_spaces`, `age_years`, `disposition`, and `orientation`.
- `parse_detail_html(source)` returns these values from dedicated feature icons and title markup.
- `map_card(..., detail=detail)` emits the v2 payload field names.

- [x] **Step 1: Add a failing fixture assertion for the supplied detail HTML: 72 covered m², one bathroom, one toilette, one parking space, three years, Frente, SE, and the page title.**
- [x] **Step 2: Run `pytest tests/unit/ops/test_import_zonaprop.py::test_parse_detail_extracts_structured_features -q` and verify the expected failure.**
- [x] **Step 3: Implement icon-aware captures and title extraction without putting structured labels into `amenities`.**
- [x] **Step 4: Add mapping assertions and change the generated envelope to `contract_version: 2`.**
- [x] **Step 5: Run the complete Zonaprop unit file and targeted Ruff check.**

### Task 3: Extend the Silver domain and pure normalizer

**Files:**
- Modify: `src/umbral/application/silver/contracts.py`
- Modify: `src/umbral/application/silver/silver_schema.py`
- Modify: `src/umbral/application/silver/service.py`
- Test: `tests/contract/test_silver_schema.py`
- Test: `tests/unit/application/silver/test_normalize_service.py`

**Interfaces:**
- `NormalizedFields` and `NormalizedListing` expose the new fields as typed nullable values plus `media_urls: tuple[str, ...]`.
- `normalize_snapshot` parses and bounds every new field using the v2 schema.
- `compare_listings` reports new numeric/category changes as attribute changes and title/media/amenity changes as text changes.

- [x] **Step 1: Add failing normalization tests for valid fields, invalid ranges, invalid URLs, and change detection.**
- [x] **Step 2: Run the focused Silver tests and confirm failures before production edits.**
- [x] **Step 3: Add minimal field parsing, error codes, URL/list bounds, and service propagation through geocoding/build helpers.**
- [x] **Step 4: Run the focused Silver unit/contract tests and verify normalizer version v2.**

### Task 4: Persist and read Silver v2 fields

**Files:**
- Modify: `src/umbral/infrastructure/db/models/silver.py`
- Create: `alembic/versions/0020_silver_listing_attributes.py`
- Modify: `src/umbral/infrastructure/db/repositories/silver.py`
- Modify: `src/umbral/infrastructure/db/repositories/radar.py`
- Modify: `src/umbral/infrastructure/db/repositories/scoring.py`
- Modify: `src/umbral/infrastructure/db/repositories/criteria.py`
- Test: `tests/migrations/test_0020_silver_listing_attributes.py`
- Test: `tests/unit/application/silver/test_canonical_repos.py`

**Interfaces:**
- `silver_listings` stores the new fields with nullable columns and bounded checks.
- Every repository mapping constructs the same `NormalizedListing` surface.
- Active listing queries include only `normalizer_version = 'silver-schema-v2'`; old v1 rows remain historical and are not candidates or API-readable listings.

- [x] **Step 1: Add failing model/repository and migration assertions, including exclusion of a v1 row from active reads.**
- [x] **Step 2: Run migration/repository tests and verify the expected missing-column/filter failures.**
- [x] **Step 3: Add the Alembic columns/checks, model attributes, insert mappings, read mappings, and active-version predicates.**
- [x] **Step 4: Run migration drift and focused repository tests.**

### Task 5: Make criteria consume structured Silver evidence

**Files:**
- Create: `contracts/criteria/v3/extraction-v3.json`
- Create: `contracts/criteria/v3/extraction-goldens-v3.json`
- Modify: `src/umbral/infrastructure/criteria/contract_loader.py`
- Modify: `src/umbral/application/criteria/extractor.py`
- Modify: `src/umbral/application/criteria/rules.py`
- Test: `tests/unit/application/criteria/test_extractor.py`
- Test: `tests/unit/application/criteria/test_rules_v2.py`
- Test: `tests/contract/test_extraction_contract.py`

**Interfaces:**
- The active extraction contract allowlists `title_text`, the new numeric/category fields, and current evidence fields.
- `run_cochera` returns true for positive `parking_spaces`, false for explicit zero, and unknown when absent.
- Existing negative-evidence semantics remain unchanged.

- [x] **Step 1: Add failing tests for permitted structured input and parking extraction from `parking_spaces`.**
- [x] **Step 2: Run those tests and confirm the active contract/rule does not yet expose the fields.**
- [x] **Step 3: Publish/load extraction v3 and implement the structured fallback in the deterministic rule.**
- [x] **Step 4: Run criteria contract and rule tests.**

### Task 6: Update source importers, fixtures, support builders, and runbooks

**Files:**
- Modify: `src/umbral/ops/import_ml.py`
- Modify: `src/umbral/ops/import_zonaprop.py`
- Modify: `src/umbral/ops/imports.py`
- Modify: `tests/support/silver.py`
- Modify: `tests/support/radar.py`
- Modify: `tests/support/criteria.py`
- Modify: affected import/Silver/radar/criteria fixtures and tests
- Modify: `docs/runbooks/import-ingestion.md`
- Modify: `docs/runbooks/silver-normalization.md`

**Interfaces:**
- Every generated batch declares import contract v2.
- Every test builder creates `SourceIdentity(..., contract_version='2')` and v2 Silver listings.
- Runbooks instruct operators to generate a fresh detail-enriched batch and normalize it with v2.

- [x] **Step 1: Add a failing test that the operational importers emit v2 and that old fixture payloads are rejected.**
- [x] **Step 2: Run focused importer/ingestion tests and confirm failure.**
- [x] **Step 3: Update all active fixtures/builders/importer envelopes and runbook commands.**
- [x] **Step 4: Run all focused import, Silver, criteria, and radar tests.**

### Task 7: Full verification and handoff

**Files:**
- Modify: only files identified by failing verification, if necessary.

- [x] **Step 1: Run focused contract, unit, and migration verification.**
- [x] **Step 2: Run targeted Ruff and mypy over changed modules.**
- [x] **Step 3: Run the available full non-integration suite and record environment/pre-existing failures separately from regressions.**
- [x] **Step 4: Run migration drift assertions and inspect `git diff --check`.**
- [x] **Step 5: Document the fresh-ingestion command and required post-deploy normalization/criteria recomputation steps.**
