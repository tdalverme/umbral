# Evidencia de cierre: Criteria and Observations (H3.1)

**Incremento**: `005-criteria-observations` | **Fecha**: 2026-08-06
**Alcance**: UM-H3-001 a UM-H3-011 (Epica H3.1 - Criterios y observaciones)
**Spec**: `specs/005-criteria-observations/spec.md` | **Plan**: `plan.md` |
**Tasks**: `tasks.md`

## Decisiones de la sesion de clarificacion (2026-08-06)

1. Una sola observacion vigente por (listing, concepto, fuente), con historial
   previo preservado (SC-012).
2. Invalidacion automatica al cambiar version; recomputo manual del operador
   con causa (FR-015/FR-016/FR-017).
3. Extraccion cualitativa en proveedor externo gestionado con input permitido
   limitado (FR-014); eleccion de proveedor concreto diferida al ADR.
4. Sin contratos HTTP en el incremento: dominio + jobs + harness; curaduria
   inicial como seed versionado (FR-024).

## Resultado por historia

| Historia | Cobertura | Evidencia |
| --- | --- | --- |
| US1 - Curaduria de conceptos | contract + unit + integration | `tests/contract/test_concept_registry.py`, `tests/unit/application/criteria/test_registry_service.py`, `tests/integration/criteria/test_product_events.py` |
| US2 - Preferencias y compilacion | contract + unit | `tests/contract/test_compilation.py`, `tests/unit/application/criteria/test_facts.py`, `test_compile_service.py` |
| US3 - Observaciones por reglas | contract + unit + integration | `tests/contract/test_extraction_rules.py`, `tests/unit/application/criteria/test_extraction_service.py`, `tests/integration/criteria/test_extraction_pipeline.py` |
| US4 - Extraccion cualitativa | unit + contract | `tests/unit/application/criteria/test_extractor.py`, `tests/unit/infrastructure/criteria/test_managed_extractor.py` |
| US5 - Recomputacion selectiva | unit + integration | `tests/unit/application/criteria/test_invalidation.py`, `tests/integration/criteria/test_recompute.py` |
| US6 - Embeddings (P1) | unit + integration | `tests/unit/application/criteria/test_embeddings.py`, `tests/integration/criteria/test_embeddings.py` |
| US7 - Contexto urbano (P1) | integration | `tests/integration/criteria/test_urban_signals.py` |

## Verificacion de Success Criteria

| SC | Verificacion | Resultado |
| --- | --- | --- |
| SC-001 versionado de conceptos | seed idempotente (6 conceptos), edicion -> version 2 sin mutar v1 | PASS |
| SC-002 casos golden de reglas | 8 casos golden (balcon, ambientes, piso, tipo_cocina) con fragmento; "sin evidencia" explicito | PASS |
| SC-003 observaciones cualitativas | schema permitido + evidencia + confianza + versiones; outputs invalidos -> `failed` con causa | PASS |
| SC-004 determinismo y recomputo selectivo | doble ejecucion identica; invalidacion solo del concepto afectado; versiones previas consultables | PASS |
| SC-005 compilacion | criterios ordenados/versionados; soft->hard sin confirmacion rechazado; confirmaciones registradas | PASS |
| SC-006 lineage 100% | walk observacion -> extraction version -> listing (normalizer_version, snapshot_id) -> Bronze | PASS |
| SC-007 embeddings (P1) | solo proyeccion permitida; 0 raw HTML/PII | PASS |
| SC-008 contexto urbano (P1) | fuente/fecha/geometria/algoritmo; precision autorizada | PASS |
| SC-009 jobs de recomputo | `recomputation_runs` con estado/conteos/causa/tiempos; fallo sin parciales | PASS |
| SC-010 eventos versionados | 4 tipos `criteria.*` en registry cerrado; payloads solo ids/versiones/conteos | PASS |
| SC-011 sin superficie HTTP | 0 routers nuevos, 0 cambios de policy, 0 cambios OpenAPI | PASS |
| SC-012 una observacion vigente | indice unico parcial `uq_listing_observations_active` + tests | PASS |
| SC-013 proveedor gestionado | adapter managed testeado con mock (4xx permanente, 5xx transitorio, input permitido) | PASS |

## Resultados de ejecucion

```text
tests/contract + unit criteria + migrations + architecture: 89 passed
tests/integration/criteria (Postgres/PostGIS/pgvector real vía testcontainers): 13 passed
```

Suite completa del repo (`pytest --ignore=tests/e2e --ignore=tests/unit/api`):
560 passed, 4 failed, 58 errores — los 4 failed y los errores son fallos de
entorno pre-existentes ajenos a este incremento (ACL de `%TEMP%` de Windows en
tests con `tmp_path`, tests de ops que dependen de PowerShell/scripts de
deploy, drift del cliente generado por npm y adapters supabase/rq), ninguno
toca superficies de criteria.

## Harness

- `scripts/check-criteria.ps1` registrado en `scripts/check.ps1` (superficie
  `src/umbral/application/criteria`).

## Diferimientos registrados

- Proveedor concreto de extraccion cualitativa y de embeddings: ADR del plan
  (el puerto, el versionado y el registro de uso estan implementados).
- Evaluadores de matcher types: H3.2 (UM-H3-013).
- Conversion de feedback en facts: H3.3 (UM-H3-028).
- Consola operativa de curaduria: H6.
