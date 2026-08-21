# Contracts: Catalogo del inmueble ideal con fuerza por usuario

## Contract: `concepts-seed-v2.json` (version `concepts-v2`)

Extiende la semántica de `concepts-seed-v1.json`. Conceptos nuevos:

| key | matcher_type | params_schema | alias de ejemplo | compute_policy |
| --- | --- | --- | --- | --- |
| `dormitorios` | numeric_range | `{min: 0, max: 100}` | dormitorios, dormis, "2 dormitorios" | computable: true |
| `banos` | numeric_range | `{min: 0, max: 20}` | banos, banio, toillette | computable: true |
| `mascotas` | categorical | `{allowed_values: [true, false]}` | acepta mascotas, pet friendly | computable: true |
| `amoblado` | categorical | `{allowed_values: [amoblado, semiamoblado, vacio]}` | amoblado, semiamoblado, con muebles | computable: true |
| `ascensor` | categorical | `{allowed_values: [true, false]}` | ascensor | computable: true |
| `cochera` | categorical | `{allowed_values: [true, false]}` | cochera, garage, parking | computable: true |
| `piscina` | categorical | `{allowed_values: [true, false]}` | piscina, pileta | computable: true |

Conceptos urbanos nuevos (signal_score):

| key | signal_ref | alias de ejemplo |
| --- | --- | --- |
| `acceso_escuela` | `school_access` | cerca de una escuela, colegio cerca |
| `acceso_deporte` | `sport_access` | cerca de un gimnasio, cancha cerca |
| `acceso_cultura` | `culture_access` | cerca de un cine, museo cerca |
| `acceso_bici` | `bike_access` | para andar en bici, ciclovia cerca |
| `acceso_salud` | `health_access` | cerca de un hospital, clínica cerca |

## Contract: `extraction-v2.json`

`allowed_input_fields` incorpora `bedrooms`. Por concepto:

| concept | source | input_fields | schema (model) / rule |
| --- | --- | --- | --- |
| `dormitorios` | rule | `[bedrooms, description_text]` | regla determinística leyendo `bedrooms` |
| `banos` | model | `[description_text, amenities]` | `{value: number, evidence, confidence}` |
| `mascotas` | rule | `[description_text, amenities]` | positivo/negativo; `unknown` si ambigüo |
| `amoblado` | model | `[description_text, amenities]` | enum amoblado/semiamoblado/vacio |
| `ascensor`/`cochera`/`piscina` | rule | `[amenities, description_text]` | mapeo amenity-string → booleano |
| urbanos | urban | `signal_ref` | source urban con `kind=urban` |

## Contract: `urban-contract-v2.json`

- `contract_version`: `urban-contract-v2`, `schema_version`: 2.
- **New categories** (en `tags_mapping` o `linear_tags_mapping` según nodo/way):
  - `school` (ways) → `linear_tags_mapping`
  - `sport_pitch` (ways) + `gym` (nodos)
  - `cinema`/`library`/`theatre` (nodos) + `museum` (ways)
  - `cycleway` (lineal) + `bicycle_parking` (nodos)
- **Existing category**: `health` ya presente.
- **New signals**:
  - `school_access`, `sport_access`, `culture_access`, `bike_access`, `health_access`
  - normalized_by: `barrio`
  - primitives: `count_300m`/`count_600m`/`nearest_m` estándar
- **New concepts** con `signal_ref` (sección de conceptos urbanos de `concepts-seed-v2.json`).

## Contract: criterio compilado (hard/soft)

- `CompiledCriterion.matcher_type` (`categorical`, `numeric_range`, `signal_score`) puede llevar `soft_to_hard: true` sólo tras confirmación (`SoftToHardRequiresConfirmation`), y `params.threshold` (0..1) para signals hard.
- `semantic_feature` nunca admite `soft_to_hard`.
- El golden dataset de matching acepta un nuevo outcome de exclusión por criterio (`excluded_criterion:<concept>`).