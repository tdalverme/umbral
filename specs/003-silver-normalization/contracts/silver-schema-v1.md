# Silver Schema v1 (Normalized Listing Contract)

**Feature**: `003-silver-normalization` | **Status**: draft for controlled beta
source | **Ratifies**: UM-H2-009, UM-H2-010, UM-H2-011, UM-H2-012 (H2.2)

Machine-checkable contract for the normalized Silver listing produced from a
Bronze snapshot. Loaded by `normalizer_version = silver-schema-v1`; immutable
once ratified. A changed contract publishes a new version; every silver row
records the `normalizer_version` that produced it.

## Normalization guarantees

- No currency conversion without a versioned rate (FR-003): the original value
  and currency are preserved as-is; a missing/unsupported rate is recorded in
  `price_assumptions`, never converted silently.
- No invented data (FR-007): missing fields stay null; unknown location stays
  `geo_precision=unknown`; no fabricated addresses or coordinates.
- No silent coercion (FR-006): an invalid/out-of-range attribute value produces
  a bounded `normalization_errors` code and a null/absent value, never a guessed
  correction.
- Change detection compares normalized fields only (FR-013): price, text,
  attributes. A `status` field is compared only when a future contract version
  defines it.

## Fields and rules

| Normalized field | Type | Rules |
| --- | --- | --- |
| `operation` | enum | `rental` only in v1 |
| `property_type` | enum | `apartment`, `house`, `room`, `studio`, `commercial`, `other` |
| `price_value` | numeric | > 0; original value, verbatim |
| `price_currency` | enum | `ARS` \| `USD`; original currency, verbatim |
| `expenses_value` | numeric | >= 0; nullable |
| `expenses_currency` | enum | `ARS` \| `USD`; nullable |
| `total_cost` | numeric | `price_value + expenses_value` when both present; else `price_value` |
| `price_assumptions` | JSONB | bounded; e.g. `{"missing_rate": "ARS->USD"}`; never fabricates a rate |
| `surface_m2` | numeric | > 0, <= 1_000_000; nullable |
| `rooms` | integer | 0..200; nullable |
| `bedrooms` | integer | 0..100; nullable |
| `floor` | integer | -10..1000; nullable |
| `amenities` | array of string | each <= 100 chars; bounded list; nullable |
| `description_text` | text | <= 20_000; nullable |
| `location_text` | string | <= 500; original text preserved verbatim |
| `neighborhood` | string | <= 200; original value, casing preserved |
| `geo_precision` | enum | `exact` \| `block` \| `neighborhood` \| `approximate` \| `unknown`; never better than the source granularity |
| `geometry` | point | nullable; only from source coordinates or a registered geocoder |
| `geo_source` | string | nullable; registered source id of the coordinates |
| `normalization_errors` | array of string | stable codes like `silver.surface_range`, `silver.rooms_type` |

## Precision assignment (location)

| Input granularity | Assigned precision | Coordinates |
| --- | --- | --- |
| Full address text + source coordinates | `exact` | source coordinates |
| Source coordinates only (no address) | `block` | source coordinates |
| Neighborhood only | `neighborhood` | none (v1) or geocoded centroid with `geo_source` |
| Partial/approximate source data | `approximate` | source coordinates if present |
| Nothing usable | `unknown` | none; never invented |

Geocoding (UM-H2-013) may resolve text to coordinates but MUST NOT raise the
assigned precision beyond the input granularity (FR-008).

## Change comparison (FR-013)

Field-level diff between consecutive chain versions compares these normalized
fields only:

- price: `price_value`, `price_currency`, `expenses_value`, `total_cost`
  (change_type `price`);
- text: `location_text`, `neighborhood`, `description_text`, `amenities`
  (change_type `text`);
- attributes: `property_type`, `surface_m2`, `rooms`, `bedrooms`, `floor`,
  `operation` (change_type `attribute`);
- `status`: only when the contract version defines it (change_type `status`).

Each diff emits one `listing_changes` row with `before`/`after`/`origin`.

## Validation codes (normalization_errors)

Stable codes, bounded list:

- `silver.surface_range` — surface outside (0, 1_000_000];
- `silver.rooms_range` — rooms outside [0, 200];
- `silver.bedrooms_range` — bedrooms outside [0, 100];
- `silver.floor_range` — floor outside [-10, 1000];
- `silver.amenities_too_long` — amenity exceeds 100 chars;
- `silver.description_too_long` — description exceeds 20_000 chars;
- `silver.url_invalid` — URL field is not a valid http(s) URL;
- `silver.currency_unsupported` — currency outside `ARS`/`USD`.

## Versioning

The contract is immutable once ratified. A changed contract publishes a new
minor (field additions) or major (breaking) revision; every silver row records
the `normalizer_version` it used. No row's recorded version changes
retroactively.
