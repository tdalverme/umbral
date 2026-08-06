# Contract: Scoring Baseline v1

**Feature**: `004-structured-search-radar` | **Date**: 2026-08-06

Versioned, immutable deterministic scoring used to order the candidate set of a
recommendation run (UM-H2-026). It is intentionally simple: objective fit over
the profile dimensions with stable tie-breaking and visible contributions. It
is NOT the H3 scoring (criteria, confidence, evidence).

## Dimensions and weights (v1)

| Dimension | Weight | Inputs |
| --- | --- | --- |
| budget | 0.40 | `budget_max`, `total_cost` |
| rooms | 0.20 | `min_rooms`, `rooms` |
| surface | 0.20 | `surface_min`, `surface_max`, `surface_m2` |
| location_precision | 0.20 | `geo_precision` of the listing |

## Fit functions (deterministic, pure)

- `budget_fit = clamp((budget_max - total_cost) / budget_max, 0, 1)` — higher
  headroom scores higher. Unknown `total_cost` never reaches scoring (hard
  filter `price -> exclude`).
- `rooms_fit`: `1.0` if `rooms == min_rooms`; `0.85` if `rooms > min_rooms`;
  `0.5` if `rooms` unknown (strategy `include`); `1.0` when `min_rooms == 0`.
- `surface_fit`: `1.0` when `surface_m2` within `[surface_min, surface_max]`
  (or `>= surface_min` when no max; `<= surface_max` when no min); `0.8` when
  above max up to 1.5x max; `0.6` above 1.5x max; `0.5` when `surface_m2`
  unknown; `1.0` when no surface bounds are set.
- `location_precision_fit` by Silver `geo_precision`: `exact` 1.0, `block`
  0.95, `neighborhood` 0.9, `approximate` 0.7, `unknown` 0.5.

## Score and tie-break

- `score = round(budget*w + rooms*w + surface*w + location*w, 4)`.
- Order: `score desc`, then `total_cost asc`, then `listing_id asc` (stable;
  same inputs always produce the same order — SC-003).
- `contributions` JSONB persisted per item: `{budget, rooms, surface,
  location_precision}` with the per-dimension fit values, plus
  `score_policy_version: "scoring-baseline-v1"`.

## Presentation rules

- Cards and list show only the total score (never the breakdown).
- The match detail shows the breakdown without asserting certainty or evidence;
  it is an approximation of objective fit (clarification 2026-08-06;
  FR-012, SC-012). Evidence-based explanations are H3.
