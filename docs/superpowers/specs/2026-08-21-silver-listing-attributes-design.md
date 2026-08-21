# Silver v2: listing attributes and source evidence

## Goal

Replace the current Silver/import contracts with a clean-cut v2 that preserves
the listing data already available in source pages and makes the structured
attributes usable by downstream criteria extraction.

The existing ingested listings are considered unusable. The runtime will accept
only import contract v2 and Silver normalizer v2; a new ingestion is required
after deployment.

## Decisions

### Contract cutover

- Active import contract: `contracts/import/v2/import-contract.json`.
- Active Silver contract: `contracts/silver/v2/silver-schema.json`.
- Active normalizer version: `silver-schema-v2`.
- `SourceIdentity` accepts only contract version `2`.
- The loaders and operational importers use v2 only. Existing v1 artifacts
  remain historical files if needed, but are not accepted or loaded by the
  runtime.

### Silver facts

Silver stores facts explicitly present in the listing payload:

- `title_text`
- `surface_m2` and `surface_covered_m2`
- `rooms`, `bedrooms`, `bathrooms`, `toilettes`, `parking_spaces`
- `floor`, `age_years`, `disposition`, `orientation`
- `amenities`, `description_text`, and `media_urls`

Missing facts stay null or empty. Invalid or out-of-range values produce a
bounded normalization error and are not coerced into a value.

### Qualitative features

Silver does not add duplicate boolean columns such as `has_pool` or
`has_elevator`. The source evidence remains in `amenities`, `description_text`,
and the structured fields. The criteria layer derives versioned
`listing_observations` from that evidence, using `true`, `false`, or `null`:

- `true` requires positive evidence;
- `false` requires an explicit negative statement;
- absence or ambiguity remains `null`.

The extraction input contract is expanded with the new Silver fields, and the
deterministic parking rule consumes `parking_spaces` so values such as
`"1 coch."` no longer depend on a text regex alone.

### Zonaprop parser

The detail parser maps the dedicated feature icons to structured fields:

- `icon-stotal` -> `surface_m2`
- `icon-scubierta` -> `surface_covered_m2`
- `icon-bano` -> `bathrooms`
- `icon-toilete` -> `toilettes`
- `icon-cochera` -> `parking_spaces`
- `icon-antiguedad` -> `age_years`
- `icon-disposicion` -> `disposition`
- `icon-orientacion` -> `orientation`
- `h1.title-property` or `og:title` -> `title`

Only qualitative page features remain in `amenities`; the full description and
image URLs are preserved.

### Existing rows

No backfill is attempted. Existing v1 Silver rows are not returned by the
active listing readers after the cutover. The new import/normalize run creates
the usable dataset from fresh Bronze snapshots.

## Acceptance criteria

1. An import payload declaring contract version `1` is rejected.
2. A v2 Zonaprop detail record contains all structured values available in the
   sample page, including covered surface, bathrooms, toilette, parking, age,
   disposition, orientation, title, description, amenities, and media URLs.
3. Silver normalization persists those values and records
   `normalizer_version = silver-schema-v2`.
4. Invalid new numeric/text values become normalization errors and null fields.
5. All Silver repositories and downstream listing readers map the new fields.
6. Old v1 rows are excluded from active listing reads.
7. Criteria permitted input includes the new fields, and the parking rule uses
   the structured value when present.
8. Fresh import, Silver normalization, and existing focused test suites pass.
