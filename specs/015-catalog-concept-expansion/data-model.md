# Data Model: Expansión del catálogo de conceptos (Fase 3)

**Date**: 2026-08-12

## Cambios al modelo existente

### CompiledCriterion (nuevo campo: `weight`)
- `weight: float` — peso del hecho de preferencia cuando el criterio proviene de un fact; para criterios de la política estática el engine usa el del policy.
- Fuente: `PreferenceFact.weight` en `compile_criteria` (facts_to_criteria).
- Contrato afectado: `contracts/criteria/v1/compilation-v1.json` (schema del criterio compilado).

### ListingObservation (nuevo valor de `source`)
- `source`: `rule` | `model` | **`urban`** (nuevo).
- Las observaciones urbanas: `value` = conteo de señales en el radio del proxy; `score` = derivado (bin o normalizado por umbral); `evidence` cita las señales (`signal_id` + `algorithm_version`).
- La fila conserva `extraction_version_id` (versión de la consolidación = versión del concepto/proxy) → la invalidación selectiva existente aplica.

### Concept (nuevo tipo de extracción)
- `concepts-seed-v1.json`: los conceptos nuevos declaran `source` de extracción (la extracción actual deriva la fuente del contrato `extraction-v1`; para urban se agrega la entrada con `source: "urban"`).
- `params_schema` del concepto urbano declara el proxy: `{"radio_m": 500, "min": 1}` — el radio alimenta la consolidación, el `min` al evaluador `numeric_range`.

## Entidades nuevas

### ExtractionGolden (contrato, no tabla)
- `contracts/criteria/v1/extraction-goldens-v1.json` (o por concepto en el seed):
  ```json
  {
    "concept_key": "moderno",
    "threshold": {"precision": 0.8, "recall": 0.7},
    "cases": [
      {"input": {"description_text": "depto renovado, cocina moderna"}, "expected": "moderno"},
      {"input": {"description_text": "edificio clasico de los 40"}, "expected": "clasico"}
    ]
  }
  ```
- Gate: el harness corre los casos contra la extracción (regla o modelo) y compara con el umbral; si falla, el concepto no se publica (observaciones no activas o bloqueo del seed en no-prod).

## Flujo de datos (ciclo completo por concepto nuevo)

```
contrato (seed + extraction + vocabulario + golden)
  → seed_registry (concepto + versión)
  → extracción/consolidación (rule | model | urban)
  → ListingObservation (source rule|model|urban, evidencia, versión)
  → compile_profile (facts → CompiledCriterion con weight + polarity)
  → score_run (engine: policy + fact params override + weight del hecho)
  → explanation (evidencia citada)
  → chat (vocabulario canónico → propose → HITL → fact)
```

## Integridad y auditoría

- El proxy es parte del contrato del concepto (versionado); cambiar el proxy = nueva versión del concepto → invalidación selectiva de observaciones urbanas de ese concepto (`recomputation_runs`).
- Las observaciones urbanas citan `signal_id` + `algorithm_version` en `evidence` para trazabilidad.
- El peso del hecho viaja en el criterio compilado (auditable por compilación).
- 0 cambios en el engine por concepto nuevo.
