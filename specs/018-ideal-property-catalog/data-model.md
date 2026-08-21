# Data Model: Catalogo del inmueble ideal con fuerza por usuario

## Entities

### Concepto de vivienda (nuevo en `concepts-v2`)

| Campo | Tipo | Notas |
| --- | --- | --- |
| `key` | string | `dormitorios`, `banos`, `mascotas`, `amoblado`, `ascensor`, `cochera`, `piscina` |
| `matcher_type` | enum | `numeric_range` (dormitorios/banos), `categorical` (mascotas/amoblado/ascensor/cochera/piscina) |
| `params_schema` | object | rangos unit (`dormitorios` 0..100, `banos` 0..20), allowed_values (`true/false`, `amoblado/semiamoblado/vacio`) |
| `defaults` | object | valores por defecto del catálogo |
| `compute_policy` | object | `computable: true` para todos; `qualitative: false` |

Fuente del dato:

| Concepto | Campo Silver | Origen |
| --- | --- | --- |
| `dormitorios` | `bedrooms` | determinístico (regla sobre `bedrooms` estructurado; vía `allowed_input_fields`) |
| `banos` | — | regla sobre `description_text`/`amenities` o modelo (schema versionado) |
| `mascotas` | — | regla sobre `description_text`/`amenities` (positivo/negativo) o modelo |
| `amoblado` | — | regla/modelo sobre `description_text`/`amenities` |
| `ascensor`/`cochera`/`piscina` | `amenities` | determinístico: mapeo de amenity-string → booleano |

### Concepto de entorno (nuevo en `concepts-v2` + `urban-contract-v2`)

| Concepto | signal_ref (v2) | Categorías OSM |
| --- | --- | --- |
| `acceso_escuela` | `school_access` | `amenity=kindergarten/school/college` (ways → `linear_tags_mapping`) |
| `acceso_deporte` | `sport_access` | `leisure=pitch/sports_centre` (ways) + `amenity=gym` (nodos) |
| `acceso_cultura` | `culture_access` | `amenity=cinema/library/theatre` (nodos) + `tourism=museum` (area) |
| `acceso_bici` | `bike_access` | `highway=cycleway` (lineal) + `amenity=bicycle_parking` (nodos) |
| `acceso_salud` | `health_access` | `amenity=hospital/clinic/doctors` (ya existente) |

### Hecho de preferencia (extensión semántica)

Reutiliza `PreferenceFact` existente; el modo no vive en el fact sino en el binding y en el `CompiledCriterion`:

| Campo | Tipo | Notas |
| --- | --- | --- |
| `binding.mode` | enum `soft`/`hard` | existente en `preferences/contracts.py` |
| `compiled.soft_to_hard` | bool | existente; ahora se propaga y se consume |
| `compiled.params.threshold` | float (0..1) | solo para signals hard (umbral percentil confirmado) |

### Evento de elevación a hard (nuevo)

| Campo | Tipo | Notas |
| --- | --- | --- |
| `event_type` | string | `preference.hard_elevated` |
| `profile_id` | UUID | radar donde se aplica |
| `concept_key` | string | criterio elevado |
| `confirmation_ref` | UUID | `HardConfirmationRef.action_id` |
| `superseded_hypothesis_ids` | UUID[] | hipótesis retiradas/superadas con trazabilidad |
| `cause` | string | declaración explícita del usuario |

## State transitions

- **Concepto**: versionado; `v1` intacto, `v2` supersede (invalida observaciones previas).
- **Hecho de preferencia**: `active` → `superseded` (revisión/retiro) — intacto; un hard confirmado no es reemplazable por learning.
- **Hipótesis**: `active/pending` → `superseded/retired` al elevar el concepto a hard (FR-012).
- **Observación urbana**: recálculo completo al publicar `urban-contract-v2` (invalidate_active_for_source).

## Persistencia

- Los nuevos conceptos viven en `concepts_seed_v2.json` y se registran vía `register_concept_version` (sin migración de esquema; las tablas son keyed por `concept_key`).
- El contrato urbano v2 se registra como `extraction_version` `kind=urban`; el snapshot y las primitivas reutilizan las tablas de 017.
- No se agregan columnas; el umbral de hard vive en `params` del compiled criterion (JSON), no en el esquema.