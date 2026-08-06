# Silver Schema v1

**Feature**: `003-silver-normalization` | **Status**: draft for controlled beta
source | **Ratifies**: UM-H2-009, UM-H2-010, UM-H2-011, UM-H2-012 (H2.2)

Machine-checkable rules live in `silver-schema.json`. `normalizer_version =
silver-schema-v1` is recorded on every Silver row that uses this contract;
immutable once ratified.

## Guarantees

- No currency conversion without a versioned rate: original value/currency
  preserved; a missing rate lands in `price_assumptions`, never converted.
- No invented data: missing fields stay null; unknown location stays
  `geo_precision=unknown`; no fabricated addresses or coordinates.
- No silent coercion: invalid/out-of-range values produce a bounded
  `normalization_errors` code and a null/absent value.
- Precision is never better than the source granularity.

## Precision assignment

| Input granularity | Assigned precision | Coordinates |
| --- | --- | --- |
| Full address + source coordinates | `exact` | source coordinates |
| Coordinates only | `block` | source coordinates |
| Neighborhood only | `neighborhood` | none or registered geocoder |
| Partial/approximate | `approximate` | source coordinates if present |
| Nothing usable | `unknown` | none |

## Change fields (FR-013)

- `price`: price_value, price_currency, expenses_value, expenses_currency, total_cost
- `text`: location_text, neighborhood, description_text, amenities
- `attribute`: property_type, surface_m2, rooms, bedrooms, floor, operation
- `status`: empty in v1; only compared when a future contract version defines it
