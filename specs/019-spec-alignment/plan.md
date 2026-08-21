# Implementation Plan: Cierre de alineacion con SPEC

**Directory**: `specs/019-spec-alignment` | **Date**: 2026-08-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/019-spec-alignment/spec.md`

## Summary

Cerrar la brecha entre SPEC.md y la arquitectura real con tres piezas
cohesivas: (1) feedback estructurado por concepto que alimenta el learning
proposals existente (ADR 0003), (2) dos conceptos economicos de regla
(`precio_m2`, `variacion_precio`) sin infraestructura nueva, y (3) un test de
integracion golden-path que demuestra los dos flujos de validacion de la SPEC.
Todo el resto de la SPEC se adapta por documentacion (Appendix A de SPEC.md +
ADRs), sin codigo especulativo.

## Technical Context

**Language/Version**: Python `>=3.13,<3.14`

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy 2, Alembic, LangGraph, PostgreSQL/PostGIS/pgvector

**Storage**: PostgreSQL; migracion 0019 sobre `feedback_event_reasons`

**Testing**: pytest (unit/contract/integration con testcontainers), harness `scripts/check.ps1`, goldens JSON versionados

**Target Platform**: API/workers Linux; desarrollo Windows con PowerShell

**Constraints** (de spec y constitucion)

- Orden final, filtros duros y notificaciones deterministas y versionados (Constitucion II).
- Dependencias hacia adentro; el dominio no importa FastAPI/DB/LLM/UI (Constitucion III).
- Cambios quirurgicos; minimo codigo que resuelve el pedido (Constitucion IV).
- 0 auto-apply: el feedback estructurado solo produce proposals HITL (spec 007).
- El counting de senales conserva el learning policy intacto (FR-004).
- El catalogo activo es `concepts-v2` (018 aun no liberado): los conceptos nuevos se agregan a la misma version; si 018 se libera antes, pasar a `concepts-v3`.
- Los conceptos semanticos/cualitativos nunca producen fuerza hard (018).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Direccion de dependencias**: PASS. Los cambios estan en `application/` (signals, service, rules) y `agent/` (tool payload); adapters en `infrastructure/`; el dominio no gana dependencias externas.
- **Agent Orchestrator con tools explicitas**: PASS. El agente interpreta con schema versionado; el servicio controlado persiste y el policy determinista decide proposals.
- **Scoring puro, determinista y versionado**: PASS. No se toca el engine; los conceptos nuevos entran por el canal de observaciones existente con goldens.
- **Persistencia fuera del chat**: PASS. Concept feedback, reasons y proposals son objetos persistentes con lineage.
- **Evidencia y explicaciones**: PASS. Cada reason nueva conserva strength/confidence/evidencia textual y las explicaciones las citan.
- **Embeddings no reemplazan hard filters**: PASS. No se usan embeddings nuevos.
- **Cambios quirurgicos**: PASS. No se rediseña ingesta, notificaciones, scoring ni identity; se extienden seams existentes.
- **Equidad**: PASS. El aprendizaje nunca genera hard; la fuerza queda documentada como evidencia, no como peso.

## Fases

1. **Phase 1**: Contratos y schema — migracion 0019 (`strength`/`confidence` en `feedback_event_reasons`), schema de interpretacion versionado en `contracts/feedback/`, tool contract del agente, events registry.
2. **Phase 2**: US1 Feedback estructurado — conformance + implementacion del puente (service `record_feedback` con `concept_feedback`, consumo en `evaluate_signals` sin tocar policy), tool del agente y evals.
3. **Phase 3**: US2 Conceptos economicos — seed `precio_m2`/`variacion_precio`, reglas deterministas, goldens, vocabulario canonico.
4. **Phase 4**: US3 Test golden-path — test de integracion de los dos flujos, bundle de harness, cierre de docs (CONTEXT si hace falta, evidence si aplica).

## Project Structure

```text
specs/019-spec-alignment/
├── spec.md
├── plan.md
└── tasks.md
```

### Source Code (repository root)

```text
src/umbral/
├── application/
│   ├── feedback/
│   │   ├── contracts.py             # FeedbackEventReason + strength/confidence
│   │   ├── service.py               # record_feedback acepta concept_feedback
│   │   └── signals.py               # verify: consumo de reasons por concepto (sin cambio de policy)
│   ├── criteria/
│   │   ├── rules.py                 # run_precio_m2, run_variacion_precio
│   │   └── registry.py              # carga del seed con conceptos nuevos
│   └── agent/tools/                 # record_feedback tool: payload concept_feedback
├── infrastructure/
│   ├── db/models/feedback.py        # columnas strength/confidence
│   └── db/repositories/feedback.py  # persistencia de reasons extendidos
└── agent/tools/tools.py             # delegacion del payload al servicio

contracts/
├── feedback/v1/                     # schema de interpretacion versionado (feedback-concept-interpret-v1.json)
├── agent/tools/                     # tool contract record_feedback (v3 o extension)
├── criteria/v2/                     # concepts-seed + extraction + goldens (precio_m2, variacion_precio)
├── criteria/v1/preferences-vocabulary-v1.json
└── events/v1/events-registry.json   # payload extendido de feedback.recorded.v1

alembic/versions/0019_feedback_strength_confidence.py
tests/
├── migrations/test_0019_feedback_strength_confidence.py
├── contract/test_feedback_concept_interpret.py
├── contract/test_extraction_goldens_v2.py      # extendido
├── unit/application/feedback/test_signals_concept.py
├── unit/application/criteria/test_rules_economic.py
├── integration/feedback/test_concept_feedback_e2e.py
└── integration/flows/test_spec_validation_flows.py
specs/019-spec-alignment/
├── spec.md
├── plan.md
└── tasks.md
```

## Milestones

- **M1** (Phase 1+2): feedback libre -> proposal HITL con evidencia. Verificacion: conformance + unit + `integration/feedback/test_concept_feedback_e2e.py` verde.
- **M2** (Phase 3): `precio_m2`/`variacion_precio` en catalogo activo con goldens y vocabulario. Verificacion: contract goldens + rules unit verde.
- **M3** (Phase 4): `tests/integration/flows/test_spec_validation_flows.py` verde en harness local. Verificacion: `./scripts/check.ps1` completo sin regresiones.