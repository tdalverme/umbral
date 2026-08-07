# Contract: Concept Registry v1

**Feature**: `005-criteria-observations` | **Date**: 2026-08-06

Curated taxonomy of matching concepts (UM-H3-001). Machine-checkable seed and
matcher-type definitions live at `contracts/criteria/v1/`:
`concepts-seed-v1.json` and `matcher-types-v1.json`. The registry is versioned:
every registration or edit produces an immutable `concept_versions` row
(FR-001). Curation enters as a versioned seed in this increment; the operator
console is H6 (FR-024).

## Concept shape

| Field | Rules |
| --- | --- |
| `key` | `^[a-z][a-z0-9_]{0,99}$`; unique |
| `name` | 1..200 chars |
| `aliases` | array of strings, max 20; resolve to one canonical concept (FR-003) |
| `matcher_type` | one of matcher-types-v1 (FR-002) |
| `params_schema` | allowed params for the matcher type (FR-002) |
| `source` | `seed` in v1 |
| `defaults` | default value/params |
| `compute_policy` | `{"unknown": "exclude"\|"penalize"\|"include", "qualitative": bool}` |

## Matcher types v1

Registered (not yet evaluated; evaluators are H3.2, UM-H3-013):

| Matcher type | Params schema (v1) | Usage |
| --- | --- | --- |
| `numeric_range` | `{min?: number, max?: number, unit?: string}` | ambientes, piso, presupuesto blando |
| `categorical` | `{allowed_values: string[]}` | tipo_cocina, estado_general |
| `geo_proximity` | `{radius_m: number}` | zonas blandas, contexto urbano |
| `semantic_feature` | `{concept: string, threshold?: number}` | features cualitativas |

## Seed concepts v1

| key | matcher_type | compute_policy | notes |
| --- | --- | --- | --- |
| `balcon` | `categorical` | unknown=penalize, qualitative=false | rule extraction (FR-010) |
| `ambientes` | `numeric_range` | unknown=penalize, qualitative=false | rule extraction |
| `piso` | `numeric_range` | unknown=penalize, qualitative=false | rule extraction |
| `tipo_cocina` | `categorical` | unknown=penalize, qualitative=false | rule extraction |
| `luminosidad` | `semantic_feature` | unknown=exclude, qualitative=true | model extraction (FR-011) |
| `estado_general` | `semantic_feature` | unknown=exclude, qualitative=true | model extraction |

## Validation rules

- A concept without a supported matcher type or with params outside the
  schema is rejected with an actionable error; nothing is persisted partially
  (FR-002).
- Alias collisions produce an explicit warning and never leave an ambiguous
  alias (FR-003).
- Every change creates a new `concept_versions` row; previous versions stay
  immutable and consultable (FR-001).
- A new concept version automatically invalidates the active observations of
  that concept (FR-015).
