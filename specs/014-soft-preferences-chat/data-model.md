# Data Model: Criterios suaves activos y chat de preferencias

**Date**: 2026-08-12

El incremento no crea tablas nuevas: reutiliza el modelo existente de criteria/feedback y agrega shapes de contrato (diff de preferencia, vocabulario). Las entidades existentes se listan con su rol en el flujo.

## Entidades existentes (rol en el flujo)

### Concept / ConceptVersion
Catálogo versionado de características evaluables. Un fact solo puede referenciar `concept_key` del catálogo activo (FK por clave + validación en servicio).
- Claves activas: `luminosidad`, `balcon`, `tipo_cocina`, `estado_general`, `ambientes`, `piso`, `barrio_seguro`.
- Relaciones: `ConceptVersion.payload` → `ExtractionVersion` (artefacto de extracción); `ListingObservation.concept_key`; `PreferenceFact.concept_key`.

### ListingObservation
Valor observado por listing+concepto con `value`, `score`, `confidence`, `evidence`, `source` (rule|model), `extraction_version_id`, `state` (active|invalidated|superseded|failed), `recomputation_run_id`.
- Restricción: único activo por (listing, concept, source).
- Rol: insumo del scoring para criterios suaves y de las explicaciones (evidencia).

### PreferenceFact
Preferencia del usuario por perfil+concepto con `polarity` (positive|negative), `weight` [0,1], `confidence` [0,1], `value` (JSONB opcional para categoricals), `fact_source`, `state` (active|superseded), `superseded_by`.
- Restricción: único activo por (profile, concept_key).
- Fuentes: `learning.confirm` (feedback aprendido) y **`chat`** (nuevo, este incremento).

### LearningProposal
Propuesta durable de cambio de preferencia: `change` (kind `preference_fact` con concept_key, polarity, suggested_weight, suggested_confidence, value), `prior_fact`, `evidence_refs`, `state` (pending|confirmed|rejected|expired|superseded), `expires_at`, `applied_profile_version_id`, `applied_run_id`.
- Rol: la tool de chat crea una con `change.kind = preference_fact`; `confirm_proposal` la aplica.

### ProfileCriteriaCompilation
Criterios ejecutables (duros del perfil + suaves desde facts) por `profile_version_id`. La compilación existente (`compile_profile`) ya incluye facts; se verifica en tareas que un fact con fuente `chat` se compile igual que `learning.confirm`.

### RecommendationRun / RecommendationItem / CriterionEvaluation
Run sobre perfil+versión compilada; items con `score`/`position`; evaluaciones por criterio para explicaciones. Sin cambios.

## Shapes nuevas (contratos)

### PreferenceChange (diff del HITL)
```json
{
  "kind": "preference_fact",
  "concept_key": "luminosidad",
  "polarity": "positive",
  "value": null,
  "suggested_weight": 0.5,
  "suggested_confidence": 0.7
}
```
- `value` solo para categoricals (`tipo_cocina`: `separada` | `integrada`).
- Pesos/confianza: defaults de `learning-policy-v1.json` (misma política que feedback).

### PreferenceProposalPayload (interrupt → frontend)
```json
{
  "type": "proposal_decision",
  "kind": "preference",
  "proposal_id": "<uuid>",
  "diff": {"concept_key": "luminosidad", "polarity": "positive", "value": null},
  "impact": {"concept": "luminosidad", "polarity": "positive", "will_recompute": true},
  "expires_at": "<iso>"
}
```

### PreferencesVocabulary (contrato versionado)
Ver [contracts/preferences-vocabulary-v1.json](./contracts/preferences-vocabulary-v1.json): alias naturales → `(concept_key, polarity, value)`.

## Transiciones de estado

- `LearningProposal`: pending → confirmed (HITL approve) | rejected (HITL reject) | expired (TTL).
- `PreferenceFact`: active → superseded (nuevo fact del mismo concepto con fuente distinta, p.ej. contradicción confirmada).
- Contradicción: al proponer polarity opuesta a un fact activo, la tool devuelve el fact vigente en `impact` y el agente pregunta antes de aplicar (FR-009); si el usuario confirma el cambio, `confirm_proposal` supersede el fact previo (`prior_fact` queda registrado).

## Integridad y auditoría

- Toda mutación pasa por correlation_id y actor (`user` para chat) y emite eventos `learning.proposal_created.v1` / `learning.proposal_confirmed.v1` (ya existentes).
- Las observaciones referencian `extraction_version_id`; al cambiar versiones, invalidación selectiva (`recomputation_runs`) sin reescrituras.
