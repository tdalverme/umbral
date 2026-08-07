# Contract: Criteria Compilation v1

**Feature**: `005-criteria-observations` | **Date**: 2026-08-06

Rules for turning preferences and structured edits into executable criteria
(UM-H3-002/003/004). Machine-checkable definitions live at
`contracts/criteria/v1/compilation-v1.json`.

## Inputs

- Profile payload (from `search_profile_versions`, immutable snapshot).
- Active `preference_facts` of the profile (value, weight, polarity,
  confidence, source).
- Structured edits: explicit, validated instructions (seed of edits in v1;
  feedback conversion is H3.3).
- Confirmations: recorded approvals for soft->hard conversions.

## Compilation semantics

- Output: an **ordered, versioned set of executable criteria** plus warnings
  (FR-007). Each criterion references `{concept_key, matcher_type, params,
  source_ref, soft_to_hard}` (FR-008).
- Criteria are validated against matcher-types-v1 and the concept
  `params_schema`; invalid criteria are rejected, never compiled (FR-002).
- Semantic memory of the profile (non-evaluable content) is **never** compiled
  into criteria without an explicit validated edit (FR-006).
- A soft preference implying a hard filter is **never** converted without a
  recorded confirmation; without it the compilation fails or warns and the
  conversion is not applied (FR-007).
- The same inputs produce the same ordered compilation (pure function;
  golden-case tested).

## Output shape

```jsonc
{
  "criteria": [
    {
      "concept_key": "balcon",
      "matcher_type": "categorical",
      "params": {"allowed_values": ["true"]},
      "source_ref": "fact:<fact_id>",
      "soft_to_hard": false
    }
  ],
  "warnings": ["alias collision ...", "soft->hard pending confirmation"],
  "confirmations": ["soft_to_hard:balcon approved by ..."]
}
```

## Persistence

- One `profile_criteria_compilations` row per (profile version,
  compilation_version); the latest version is the effective compilation
  (R-03). Compilation creation emits `criteria.compilation_created.v1`.
- Compilations are consumed later by the scoring engine (H3.2) via domain, not
  HTTP (FR-024).
