# Contract: Comparison v1

**Feature**: `006-scoring-explanations` | **Date**: 2026-08-07

Structured comparison of listings of the same radar (UM-H3-020, UM-H3-022 P1).
No winner is ever computed (US8.5, FR-016).

## Request / Response

`POST /api/v1/search-profiles/{search_profile_id}/comparisons`

```json
{
  "listing_ids": ["uuid", "uuid", "uuid"]
}
```

Response `Comparison`:

```json
{
  "search_profile_id": "uuid",
  "run_id": "uuid",
  "score_version": "scoring-policy-v1",
  "limit": 6,
  "listings": [{"listing_id": "uuid", "position": 0}],
  "dimensions": [
    {"kind": "fixed", "key": "total_cost", "label": "precio total"},
    {"kind": "fixed", "key": "expenses", "label": "expensas"},
    {"kind": "fixed", "key": "surface_m2", "label": "superficie"},
    {"kind": "fixed", "key": "rooms", "label": "ambientes"},
    {"kind": "fixed", "key": "bedrooms", "label": "dormitorios"},
    {"kind": "fixed", "key": "location", "label": "ubicacion / precision"},
    {"kind": "fixed", "key": "score", "label": "score"},
    {"kind": "criterion", "key": "presupuesto", "concept": "presupuesto"},
    {"kind": "criterion", "key": "luminosidad", "concept": "luminosidad"}
  ],
  "cells": [
    {
      "listing_id": "uuid",
      "dimension_key": "total_cost",
      "value": 450000,
      "state": "match",
      "missing": false,
      "evidence_refs": [{"kind": "listing_field", "ref": "total_cost", "version": "silver-v1"}]
    }
  ]
}
```

## Rules (FR-016/FR-017, R-10)

- `listing_ids` MUST contain 2..`limit` distinct ids (`limit` default 6,
  setting `scoring.comparison_max_listings`); otherwise 400
  `comparison_limit_exceeded` / `comparison_duplicate_listing`.
- Every listing MUST belong to the latest published run of the profile (the
  ownership boundary); otherwise 403 `comparison_not_in_radar` (deny-by-default,
  no data leaked).
- The run MUST be `succeeded`; a legacy run returns 400 `explanation_unavailable`
  (comparison needs evaluations).
- Dimensions: fixed basics (total cost, expenses, surface, rooms, bedrooms,
  location/precision, score + confidence) plus the profile's active criteria
  from the run evaluations, each cell carrying value, `state`
  (match/mismatch/unknown), `missing` flag and `evidence_refs`.
- Missing cells render as missing; never as 0 or mismatch (FR-016, US8.2).
- No aggregate/winner row is computed or returned.
- Emits `recommendation.comparison_viewed.v1` (client) on success.

## Shortlist (P1, UM-H3-022)

- `GET /api/v1/search-profiles/{id}/comparison-shortlist` — persisted list
  (table `comparison_shortlists`, R-10).
- `PUT /api/v1/search-profiles/{id}/comparison-shortlist` `{"listing_ids": [...]}`
  — idempotent replace; validates membership like the comparison; returns the
  stored list.
- The matrix view consumes this list and `POST comparisons`; navigation to the
  listing detail is preserved (US10.3).

## UI presentation

- Responsive matrix: fixed dimensions first, criteria rows grouped below,
  sticky listing header; cells with missing data show an explicit "sin datos"
  state; each cell links to the listing detail when meaningful (US10.4,
  FR-020).
- The comparator is P1: ordered after the first internal pass of the hito;
  `scoring.comparator_enabled=false` default.
