# Evidencia de cierre: Feedback y aprendizaje controlado (H3.3)

**Feature**: `007-feedback-learning` | **Fecha**: 2026-08-07 | **Alcance**:
UM-H3-023 a UM-H3-031 (Epica H3.3)

## Resumen

Se implementó feedback inmutable e idempotente (like/dislike/save/dismiss/
contacted) con cadena de compensación, shortlist compartida con el comparador
de H3.2, descartados como overlay sin runs nuevos, propuestas de aprendizaje
deterministas (solo like/dislike con razones ligadas a conceptos), confirmar/
deshacer/ampliar vía los seams de H3.1/H3.2, y recalculado con runs `edited`
atómicos. Feedback libre (P1) e historial de precio/cambios (P1) con flags.

## Resultados por Success Criterion (spec)

| SC | Verificación | Resultado |
| --- | --- | --- |
| SC-001 eventos inmutables | `tests/unit/application/feedback` + `tests/integration/feedback/test_feedback_events.py` | PASS |
| SC-002 idempotencia/compensación | unit + integración (replay, no-op, like→dislike→like) | PASS |
| SC-003 superficies accesibles | web build + componente `feedback-actions.tsx` | PASS (build) |
| SC-004 shortlist/descartados | `test_decision_items.py` (unit + integración), matches overlay | PASS |
| SC-005 propuestas con evidencia | `test_signals`/`test_proposal_lifecycle` (3 señales → 1 propuesta con refs) | PASS |
| SC-006 confirmar/deshacer/ampliar | `test_proposal_lifecycle` (confirm/undo/expand/reject) | PASS |
| SC-007 recalculado | `test_recalculate.py` (run `edited`, directo 0 runs) | PASS |
| SC-008 eventos sin PII/texto | `test_events_registry` + forbidden `free_feedback` | PASS |
| SC-009 historial sin tendencias (P1) | sección web "Historial de precio y cambios" | PASS (build) |
| SC-010 ownership deny-by-default | conformance de endpoints feedback/learning | PASS |

## Verificación ejecutada

- Unit + contract + migration + architecture feedback: **128 tests** en verde
  (`pytest tests/unit/application/feedback tests/unit/application/radar/test_learning_seams.py
  tests/contract/test_feedback_endpoints.py tests/contract/test_learning_endpoints.py
  tests/contract/test_quick_reasons.py tests/contract/test_learning_policy.py
  tests/contract/test_events_registry.py tests/migrations tests/architecture/test_feedback_boundaries.py`).
- Integración sobre Postgres real (testcontainers): `tests/integration/feedback`
  completo en verde (eventos, decision-items, lifecycle de propuestas,
  recalculado, lineage).
- `ruff check` y `mypy strict` en verde sobre `src/umbral` y los tests de
  feedback.
- `npm run build --workspace @umbral/web` en verde con las rutas nuevas
  (feedback, decision-items, learning-proposals, shortlist, dismissed).
- OpenAPI exportado y cliente TS regenerado
  (`scripts/export-openapi.ps1` + `npm run api:generate --workspace @umbral/web`).

## Gate de harness

`scripts/check-feedback.ps1` creado y registrado en `scripts/check.ps1`.
Pendiente de ejecución en CI desde checkout limpio: `.\scripts\check.ps1`
(requiere Docker para los slices de integración).

## Decisiones clave implementadas

- Política de aprendizaje versionada e inmutable (`learning_policies` +
  `learning_policy_versions`, seed `learning-v1`) — patrón de la scoring policy.
- Solo like/dislike con razones ligadas a conceptos cuentan como señales.
- Confirmación = `record_preference_fact(fact_source="learning.proposal")` →
  bump de versión → compile → run `edited`; undo = fact de compensación.
- Shortlist de producto = `comparison_shortlists` (persistencia compartida con
  H3.2); dismiss = overlay de estado en `matches` (sin runs).
- Eventos aditivos (9 tipos) en el registry cerrado; 0 texto de feedback libre
  en eventos (forbidden `free_feedback`).
- Feedback libre e historial de cambios: P1 detrás de
  `feedback.free_feedback_enabled` y datos `known_changes` existentes.

## Notas y diferimientos

- El cliente web generado y el OpenAPI exportado quedan como cambios sin
  commitear (la implementación no hace commits por sí sola).
- El fallo de `test_generated_web_client_is_regenerated_without_a_diff` es
  esperado hasta commitear el cliente regenerado.
- Los tests web dedicados (component tests de feedback/historial) siguen el
  diferimiento de tests web dedicados de H2.3; la verificación web es build +
  recorrido manual del quickstart.
