# Contract: Explanations v1

**Feature**: `006-scoring-explanations` | **Date**: 2026-08-07

Machine-checkable: `contracts/scoring/v1/explanations-v1.json` (reason codes,
evidence levels, copy template keys).

Explanations are generated deterministically from the frozen run data
(evaluations, run snapshots, policy) by pure templates (clarification
2026-08-07; FR-012/FR-013). No generative text in v1.

## Explanation document (API response shape)

```json
{
  "search_profile_id": "uuid",
  "run_id": "uuid",
  "listing_id": "uuid",
  "score_version": "scoring-policy-v1",
  "score": 0.72,
  "confidence": 0.66,
  "profile_snapshot": {"profile_version_id": "uuid", "policy_version_id": "uuid"},
  "feature_snapshot": {"evaluation_version_key": "run:uuid:listing:uuid"},
  "reasons": [
    {
      "criterion_key": "presupuesto",
      "state": "match",
      "score": 0.9,
      "confidence": 1.0,
      "contribution": 0.225,
      "evidence_level": "strong",
      "reason_code": "budget_within_headroom",
      "evidence_refs": [{"kind": "listing_field", "ref": "total_cost", "version": "silver-v1"}]
    }
  ],
  "risks": [
    {"criterion_key": "luminosidad", "state": "unknown", "reason_code": "no_observation_data"}
  ],
  "missing_data": [{"criterion_key": "luminosidad", "concept": "luminosidad"}],
  "satisfied_filters": ["budget_max", "zones", "min_rooms"]
}
```

## Reason codes (deterministic keys -> copy template keys)

| state | Reason code | Copy intent |
| --- | --- | --- |
| match | `budget_within_headroom` | "dentro del presupuesto con margen" |
| match | `rooms_match` / `rooms_above_min` | ambientes esperados / por encima del minimo |
| match | `surface_within_bounds` | superficie dentro del rango |
| match | `location_near_preferred` | ubicacion cercana a la preferida |
| match | `concept_observed` | el concepto se observo en el listing (evidencia) |
| mismatch | `budget_over_max` | supera el presupuesto |
| mismatch | `concept_missing` | el concepto no se cumple (evidencia negativa) |
| unknown | `no_observation_data` | sin datos suficientes: no se evaluo |
| unknown | `location_precision_low` | ubicacion con precision baja: no se pudo evaluar |

Copy templates live in the contract file; product reviews wording per
UM-H0-007. Templates MUST NOT assert facts absent from `evidence_refs`
(FR-013, SC-007).

## Evidence levels

- `strong`: confidence >= `strong_threshold` (0.8 default).
- `medium`: >= `medium_threshold` (0.5).
- `low`: below medium; includes every `unknown` evaluation.
- Scores are always presented with their confidence and level; never as
  certainty (FR-018).

## API surface (R-09)

- `GET /api/v1/search-profiles/{search_profile_id}/explanations/{listing_id}?run_id=`
  - 200 explanation; 404 `explanation_unavailable` for legacy runs
    (`score_policy_version = scoring-baseline-v1`); 404/403 by ownership;
    400 for run state not `succeeded`.
- `GET /api/v1/search-profiles/{search_profile_id}/explanations?run_id=&page_size=&after_position=`
  - paginated over the run's items (same keyset as matches); each item embeds
    the top reasons (up to 3) for cards, plus score, confidence and
    evidence level.
- Errors use the typed problem+json shape of the existing product routers
  (`application/problem+json`, `code` field).
- Every successful view emits `recommendation.explanation_viewed.v1` (client,
  R-11) with ids/counts only.
