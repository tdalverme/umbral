# ADR 0003: Feedback estructurado por concepto

**Status**: Aceptado
**Date**: 2026-08-20
**Owner**: team-product
**Version**: 1.0.0
**Spec**: SPEC.md §20.1, §28.2, §28.5; implementado en `specs/019-spec-alignment`.

## Context

SPEC.md exige que el lenguaje de feedback se interprete en senales
estructuradas por concepto ("me gusta, pero la cocina es chica e integrada" →
`kitchen_size = negative/strong`, `kitchen_openness = negative/medium`), que
el LLM interprete el significado y que un servicio controlado decida cuanto
cambia el modelo de preferencia (§20.1). El caso de rechazo ("por que me lo
recomendaste?") tambien debe traducirse a aprendizaje estructurado (§28.5).

Hoy el repo registra feedback inmutable (`FeedbackEvent`) con razones curadas
(`FeedbackEventReason` con `reason_key`, `concept_id`, `polarity`) y texto
libre cualitativo que no alimenta senales (`free_feedback`). El motor de
aprendizaje (`feedback/signals.py`) ya cuenta senales por `concept_key` +
`polarity` en ventanas versionadas (`min_signals`, cooldown, expiry) y produce
`LearningProposal` con confirmacion HITL (0 auto-apply, spec 007). Falta el
puente: un feedback libre interpretado por concepto que llegue a ese motor.

## Decision drivers

- Reusar el machinery existente: `evaluate_signals` ya consume senales por
  concepto/polaridad; `FeedbackEventReason` ya referencia conceptos.
- Policy determinista intacto: el learning policy (007) no cambia; la
  fuerza no modula el conteo en V1.
- El LLM solo interpreta; nunca asigna pesos finales (Constitucion II).
- Conceptos fuera de catalogo: se preservan como texto (patron 016), nunca
  se inventan conceptos.

## Alternatives considered

| Alternativa | Costo | Resultado |
| --- | --- | --- |
| Mapear el feedback libre a `reason_keys` existentes, sin schema nuevo | bajo | pierde concepto y fuerza; no satisface §20.1/§28.2 | rechazada |
| Extender `record_feedback` con `concept_feedback[]` versionado, columnas `strength`/`confidence` en `feedback_event_reasons`, alimentando `evaluate_signals` | medio: payload nuevo + migracion 0019 + tool contract | satisface SPEC, reusa proposals/HITL | **elegida** |
| Aplicacion directa (feedback fuerte → fact sin confirmacion) | bajo | viola 0 auto-apply y la autoridad (explicito > feedback deliberado) | rechazada |

## Decision

1. **El tool `record_feedback` acepta `concept_feedback[]`**: cada entrada
   con `concept_key`, `polarity` (positive|negative), `strength`
   (low|medium|strong) y `confidence` (0..1), producida por interpretacion
   estructurada versionada del lenguaje libre (mismo patron de
   `preference-interpret`); el LLM nunca elige conceptos ni pesos.
2. **Persistencia**: migracion 0019 agrega `strength` y `confidence` a
   `feedback_event_reasons`; el fragmento de evidencia del texto persiste en
   `free_feedback` con la traza al evento (0 PII en analytics).
3. **Aprendizaje**: los `FeedbackEventReason` con concepto alimentan el
   `evaluate_signals` existente (conteo por polaridad; `strength`/`confidence`
   se conservan como evidencia pero no modulan el counting en V1); el umbral
   del learning-policy versionado se mantiene; la `LearningProposal` resultante
   requiere confirmacion HITL como hoy.
4. **Elegibilidad**: solo conceptos del catalogo activo y computables;
   conceptos desconocidos → conservacion como deseo/frase no evaluable
   (patron 016) con puente sugerido; ninguna creacion de concepto por chat.
5. **Contratos versionados**: schema de interpretacion nuevo en
   `contracts/feedback/`, tool contract del agente actualizado (v3 o
   extension segun convencion), y registry de eventos ajustado para el
   payload extendido.

## Consequences

- El feedback libre deja de ser un callejon sin uso: llega a proposals con
  evidencia y HITL, igual que las razones curadas.
- El learning policy, el scoring y las notificaciones no cambian.
- Los goldens del agente y las trayectorias deben cubrir el nuevo payload
  (evals y abuse suite).
- La fuerza queda documentada como senal para recalibraciones futuras, no
  como peso activo.

## Monitoring

- Tasa de feedback con `concept_feedback` vs `reason_keys` curadas; tasa de
  `unknown`/no-evaluables; tasa de proposals generadas y confirmadas.
- Evals de trayectorias: el flujo §28.2/§28.5 entra al conjunto golden.

## Compliance

- 0 auto-apply; authority intacta (explicito > feedback deliberado > pasivo).
- Sin cambios en ranking ni notification decision (decisiones por codigo
  versionado).