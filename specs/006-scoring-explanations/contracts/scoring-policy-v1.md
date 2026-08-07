# Contract: Scoring Policy v1

**Feature**: `006-scoring-explanations` | **Date**: 2026-08-07

Machine-checkable: `contracts/scoring/v1/scoring-policy-v1.json`.

The scoring policy is the single authority over how a profile is combined with
a listing in scoring v1 (FR-001/FR-002/FR-003). It is persisted as immutable,
append-only versions (`scoring_policy_versions`) validated against this
contract; the curated seed `scoring-policy-v1` is loaded at startup.

## Policy document (payload)

```json
{
  "contract_version": "1",
  "score_policy_version": "scoring-policy-v1",
  "normalization": "weighted_sum",
  "score_round": 4,
  "confidence": {
    "unknown_penalty": 0.2,
    "strong_threshold": 0.8,
    "medium_threshold": 0.5
  },
  "criteria": [
    {
      "key": "presupuesto",
      "concept": "presupuesto",
      "matcher_type": "numeric_range",
      "weight": 0.25,
      "params": {"min": 0, "max": 1, "unit": "ars"},
      "gate": null
    },
    {
      "key": "ambientes",
      "concept": "ambientes",
      "matcher_type": "numeric_range",
      "weight": 0.15,
      "params": {"min": 0, "max": 200, "unit": "rooms"},
      "gate": null
    },
    {
      "key": "superficie",
      "concept": "superficie",
      "matcher_type": "numeric_range",
      "weight": 0.15,
      "params": {"min": 0, "max": 2000, "unit": "m2"},
      "gate": null
    },
    {
      "key": "ubicacion",
      "concept": "ubicacion",
      "matcher_type": "geo_proximity",
      "weight": 0.20,
      "params": {"radius_m": 1500},
      "gate": null
    },
    {
      "key": "balcon",
      "concept": "balcon",
      "matcher_type": "categorical",
      "weight": 0.10,
      "params": {"allowed_values": ["si"]},
      "gate": "cap_0.6_on_mismatch"
    },
    {
      "key": "luminosidad",
      "concept": "luminosidad",
      "matcher_type": "semantic_feature",
      "weight": 0.10,
      "params": {"concept": "luminosidad", "threshold": 0.5},
      "gate": null
    },
    {
      "key": "estado_general",
      "concept": "estado_general",
      "matcher_type": "semantic_feature",
      "weight": 0.05,
      "params": {"concept": "estado_general", "threshold": 0.5},
      "gate": null
    }
  ],
  "bonuses": [{"criterion": "balcon", "state": "match", "delta": 0.03}],
  "penalties": [{"criterion": "presupuesto", "state": "mismatch", "delta": 0.1}],
  "tie_break": ["score", "total_cost_asc", "listing_id_asc"]
}
```

## Validation rules (FR-002)

- `contract_version` MUST be `1`; `score_policy_version` MUST be non-empty.
- `criteria` MUST contain 1..N entries with `key`, `matcher_type`, `weight`,
  `params`; `key` MUST be unique.
- `matcher_type` MUST exist in `matcher-types-v1.json`; `params` MUST be a
  subset of that type's `allowed_params`.
- Concept references MUST exist in the curated concept registry seed
  (`concepts-seed-v1.json`) or be one of the fixed criteria
  (`presupuesto`, `ambientes`, `superficie`, `ubicacion` — evaluated from
  profile fields and listing data instead of observations).
- Weights MUST normalize: `abs(sum(weights) - 1) <= 1e-6` (rejects
  "pesos no normalizables").
- `score_round` MUST be 2..6. `gates` MUST be one of the supported gate kinds
  (`cap_<value>_on_mismatch`, `cap_<value>_on_unknown`, `exclude_on_mismatch`)
  or null.
- `bonuses`/`penalties` MUST reference existing criterion keys and states
  (`match`, `mismatch`, `unknown`); deltas MUST be in `[-0.2, 0.2]`.
- `tie_break` MUST start with `score` and use only supported keys
  (`score`, `total_cost_asc`, `listing_id_asc`).
- Invalid documents are rejected with an actionable error; nothing persists
  partially (FR-002).

## Semantics

- `normalization = weighted_sum`: `score = clamp(sum(weight_i * score_i) +
  bonuses - penalties, 0, 1)`, rounded to `score_round`. Score scale is 0..1,
  inherited from the baseline (R-01; spec assumption).
- `unknown` evaluations contribute neutrally (weight is not applied) and lower
  the run confidence via `confidence.unknown_penalty` per unknown (R-04,
  FR-006).
- `match`/`mismatch` always carry evidence; `unknown` never counts as a
  mismatch.
- Gates modify the item score/eligibility deterministically (e.g. a `balcon`
  mismatch caps the item score at 0.6).
- Confidence per evaluation: `numeric_range`/`categorical` = 1.0 when the
  observation exists, 0.0 when unknown; `geo_proximity` scaled by location
  precision (exact 1.0 .. unknown 0.0); `semantic_feature` = observation
  confidence. Run confidence = mean of evaluation confidences after the
  unknown penalty.
- Evidence levels for the UI: `strong >= 0.8`, `medium >= 0.5`,
  `low < 0.5` (contract defaults; thresholds live in the policy document).

The exact seed values are product curation, reviewed with the 
`UM-H0-007` evidence policy; the contract defines the shape, the seed file
defines the values.
