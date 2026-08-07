# Evidencia de aceptación: Scoring y explicaciones (H3.2)

**Fecha**: 2026-08-07 | **Incremento**: `006-scoring-explanations`
| **Alcance**: UM-H3-012 a UM-H3-022

## Decisiones de la sesión de clarificación (2026-08-07)

- Copy de explicaciones 100% determinista por templates; sin LLM en v1
  (UM-H3-018).
- Runs congelados vigentes: sin invalidación automática por cambios de
  observaciones/datos Silver en H3.2; recálculo automático es H3.3
  (UM-H3-030).
- Runs legacy del baseline (H2.3) siguen visibles con score sin desglose y
  aviso `explanation_unavailable`; sin migración ni backfill.
- Dimensiones del comparador: fijas básicas + criterios activos del perfil.

## Resultado por historia

- **US1 policy v1**: `test_scoring_policy.py` + `test_policy_service.py`
  (seed idempotente, versionado append-only, rechazo de documentos inválidos
  sin parciales).
- **US2 evaluadores**: `test_evaluators.py` + `test_evaluation_service.py`
  (goldens por matcher type, contrato común, unknown sin inventar puntaje).
- **US3 desconocido vs negativo**: `test_unknown_semantics.py` (desconocido
  baja confianza, 0 mismatch, serialización distinguible).
- **US4 scoring determinista**: `test_run_scoring.py` (doble ejecución
  idéntica, input_refs versionados, contribución y razón).
- **US5 runs atómicos**: `test_run_publish.py` + `tests/integration/scoring/
  test_run_v1.py` (publicación run+items+evaluaciones+evento en una
  transacción, fallo sin parciales, legacy intacto, recompute no invalida).
- **US6 explicaciones**: `test_explanations.py` + `test_explanation_service.py`
  (copy determinista, evidence refs, riesgos y faltantes del breakdown).
- **US7 contrato de explicación**: `test_explanation_endpoints.py`
  (per-listing y lista paginada, deny-by-default, errores tipados).
- **US8 comparación**: `test_comparison.py` + `test_comparison_service.py`
  (límite, duplicados, membership del run, 0 ganador).
- **US9 web**: cards con ≤3 razones y badges de evidencia, detalle con
  desglose, notice de legacy, score+confianza, eventos de vista; build web
  verde.
- **US10 comparador (P1)**: `test_shortlist_service.py` + ruta
  `radar/[id]/compare` con matriz responsive y shortlist persistente
  (`scoring.comparator_enabled=false` por default).

## Verificación de Success Criteria

| SC | Evidencia |
| --- | --- |
| SC-001 determinismo (doble ejecución idéntica) | `test_run_scoring.py::test_identical_inputs_produce_identical_order_and_breakdown` |
| SC-002 policy versionada inmutable | `test_policy_service.py` + conformance de rechazo |
| SC-003 evaluadores golden | `test_evaluators.py` (24 casos) |
| SC-004 unknown vs negativo | `test_unknown_semantics.py` |
| SC-005 evaluaciones con inputs versionados | `test_run_scoring.py::test_evaluations_carry_versioned_input_refs_and_reason` |
| SC-006 runs atómicos, 0 invalidación | `test_run_publish.py` + `test_run_v1.py` (integración) |
| SC-007 explicaciones con evidence refs y copy determinista | `test_explanations.py` + `test_explanation_service.py` |
| SC-008 deny-by-default en explicación | `test_explanation_endpoints.py` + `test_explanation_service.py` |
| SC-009 comparación con límite, faltantes, 0 ganador | `test_comparison.py` + `test_comparison_service.py` |
| SC-010 eventos versionados sin PII | `test_events_registry.py` (2 tipos nuevos + forbidden keys) |
| SC-011 web distingue evidencia, nunca certeza | component tests pendientes (ver diferimientos) + build verde |
| SC-012 shortlist persistente (P1) | `test_shortlist_service.py` + integración `test_lineage.py` |

## Resultados de ejecución (local, 2026-08-07)

- Contract conformance scoring (policy, evaluators, explicaciones,
  comparación, endpoints, eventos, arquitectura): **verde**.
- Unit tests `tests/unit/application/scoring`: **30/30 verde**.
- Migración `0007` (head único, drift, downgrade): **verde**.
- Suite existente contract/unit/architecture/migrations: **481 passed**
  (4 fallos pre-existentes ajenos al incremento: `test_generated_client`
  por trabajo de 005 sin commitear, `test_supabase_adapter` y `test_cli`
  por entorno; `test_upgrade_and_drift` actualizado al nuevo head 0007).
- Build web (`npm run build --workspace @umbral/web`): **verde**.
- Cliente TS regenerado desde OpenAPI exportado
  (`scripts/export-openapi.ps1` + `npm run api:generate`).

## Harness

`scripts/check-scoring.ps1` creado y registrado en `scripts/check.ps1`
(surface `Scoring`): contract conformance + unit + integración scoring sobre
testcontainers + migración 0007.

## Diferimientos registrados

- Component tests web dedicados (cards/detalle/comparador con vitest): siguen
  el diferimiento de H2.3 (tests web dedicados pendientes de seguimiento);
  la verificación web local es build + recorrido manual del quickstart.
- Integración de scoring (run v1, lineage, shortlist) requiere
  Postgres/PostGIS real vía testcontainers: corre en CI (mismo patrón que
  criteria).
- Copy final de incertidumbre: revisión con producto según UM-H0-007 antes
  del release.
- `test_generated_client` (drift del cliente vs OpenAPI) queda sujeto al
  commit del incremento 005 pendiente en el working tree.
