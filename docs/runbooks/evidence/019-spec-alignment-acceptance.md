# Evidencia de cierre: Alineacion con SPEC (019)

**Feature**: `specs/019-spec-alignment` | **Fecha**: 2026-08-21

## Alcance

Este incremento cierra tres brechas verificables de `SPEC.md`:

- feedback estructurado por concepto, con `strength` y `confidence`, que
  conserva evidencia y alimenta propuestas HITL sin auto-aplicar cambios;
- `precio_m2` y `variacion_precio` como observaciones deterministas con
  evidencia y estado `unknown` cuando faltan datos;
- un golden path de integración que recorre persistencia, ranking,
  explicación, feedback, propuesta, confirmación, nuevo run e idempotencia.

Los ADRs [0002](../../decision-records/0002-session-scoping.md) y
[0003](../../decision-records/0003-structured-concept-feedback.md) fijan el
alcance: no se agregan imágenes, comparables, `days_on_market`, `price_drop`,
session overrides reales ni una capa observación->derivado.

## Evidencia por historia

| Historia | Evidencia | Resultado esperado |
| --- | --- | --- |
| US1 - feedback por concepto | `tests/contract/test_feedback_concept_interpret.py`, `tests/unit/application/feedback/test_concept_signals.py`, `tests/integration/feedback/test_concept_feedback_e2e.py` | PASS con Postgres disponible |
| US2 - conceptos económicos | `tests/unit/application/criteria/test_rules_economic.py`, `tests/contract/test_extraction_goldens.py` | PASS |
| US3 - golden path | `tests/integration/flows/test_spec_validation_flows.py` | PASS con Postgres disponible |

## Harness

El bundle `scripts/check-019.ps1` quedó registrado en `scripts/check.ps1` y
ejecuta los contratos, unit tests y los dos slices de integración de esta
spec. Usa el mismo Postgres de Testcontainers que el resto del repositorio.

En el entorno de desarrollo de esta ejecución, los tests puros y contract
pasaron; los slices que requieren Testcontainers no pudieron iniciar porque
el daemon Docker devolvió `Acceso denegado` sobre
`//./pipe/docker_engine`. La verificación final queda lista para CI o para
un entorno local con Docker habilitado. `specify.exe` tampoco está instalado
en este checkout.

## Invariantes preservados

- el ranking final, los filtros duros y las explicaciones siguen siendo
  deterministas y versionados;
- `strength`/`confidence` no modulan `min_signals`, la ventana ni el conteo;
- el feedback estructurado solo crea `LearningProposal` pendiente;
- los conceptos semánticos nunca generan fuerza hard;
- los eventos no incorporan texto libre ni PII.
