# Implementation Plan: Criterios suaves activos y chat de preferencias

**Branch**: `014-soft-preferences-chat` | **Date**: 2026-08-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-soft-preferences-chat/spec.md`

## Summary

El radar actual solo ejercita filtros duros: la capa de criterios suaves (conceptos, observaciones, preference facts) existe pero está dormida (concepts/observations vacíos, seed local incompleto). Este incremento (Fase 0 + Fase 1 del roadmap) la activa de punta a punta y conecta el chat a las preferencias:

1. **Fase 0 — Activar la capa suave**: sembrar el catálogo de conceptos y versiones de extracción desde contratos publicados, correr la extracción (reglas determinísticas + cualitativos estructurados con evidencia/confianza), y verificar que la compilación del perfil y el scoring consumen criterios suaves con explicaciones que citan evidencia. El seed local deja el stack completo activo con un comando.
2. **Fase 1 — Chat de preferencias**: nueva tool `propose_search_preference_update` que traduce vocabulario canónico natural a conceptos por código (0 adivinanza del LLM), crea una propuesta durable pendiente (HITL reusando el patrón de proposals), y al confirmar registra un PreferenceFact con fuente "chat", recompila y recomputa reutilizando el flujo de confirmación de aprendizaje existente (`FeedbackService.confirm_proposal`).

## Technical Context

**Language/Version**: Python 3.13 (pyproject), TypeScript 5.x / Next.js App Router (web)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 + Alembic, LangGraph (topology v3), Pydantic; web: TanStack Query, shadcn/ui

**Storage**: PostgreSQL 17 con PostGIS y pgvector

**Testing**: pytest (unit/contract/integration + harness `scripts/check.ps1`), ruff, mypy estricto; web: vitest + eslint + tsc

**Target Platform**: Linux server (API + workers), navegador (web)

**Project Type**: monolith modular (monorepo con `apps/web` y `src/umbral`)

**Performance Goals**: extracción batch en worker; turno de chat < 5s (ya acotado por budget/tool timeouts)

**Constraints**: 0 LLM en ranking/valores; toda mutación con HITL e idempotencia; evidencia/confianza/versión en observaciones y facts; capas: agent → application → domain (sin infra en dominio)

**Scale/Scope**: beta privada CABA; catálogo actual de conceptos; sin embeddings/urban signals en este incremento

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Regla | Cumple |
|------|-------|--------|
| I. Persistent Radar as Product Truth | Las preferencias viven como facts persistentes (no solo en el chat); la propuesta es durable y auditable | Sí — PreferenceFact + LearningProposal durables |
| II. Auditable Deterministic Matching | Traducción vocabulario→concepto por código versionado; scoring determinístico; 0 LLM en valores | Sí — `preferences-vocabulary-v1` + flujos existentes |
| III. Layered Dependency Direction | Agent tools delegan en application services; dominio sin infra | Sí — tool → CriteriaService/FeedbackService |
| IV. Minimal, Verifiable Change | Reuso de LearningProposal/HITL/compile/recompute; verificación por incremento | Sí — sin abstracciones nuevas |
| V. Data Lineage and Trust | Facts con fuente, correlation, versiones; observaciones con evidencia/confianza | Sí — shapes existentes + fuente "chat" |

## Project Structure

### Documentation (this feature)

```text
specs/014-soft-preferences-chat/
├── plan.md              # This file
├── research.md          # Phase 0 output (decisiones de diseño)
├── data-model.md        # Phase 1 output (entidades y relaciones)
├── quickstart.md        # Phase 1 output (guía de validación)
├── contracts/           # Phase 1 output (vocabulario canónico publicado)
├── checklists/          # Quality checklists
├── spec.md              # Feature specification
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
src/umbral/
├── agent/
│   ├── intent/
│   │   └── compiler.py          # + vocabulario canónico de preferencias
│   ├── tools/
│   │   ├── tools.py             # + tool propose_search_preference_update
│   │   └── registry.py          # (sin cambios; contrato v2 rige)
│   └── graph.py                 # + routing HITL para preferencias (resolve_decision)
├── application/
│   ├── agent/
│   │   └── tools/
│   │       ├── contracts.py     # + PreferenceProposalError si aplica
│   │       └── preferences.py   # NUEVO: traducción canónica → concepto (puro, versionado)
│   └── criteria/
│       └── service.py           # (sin cambios; seed_registry/process_extraction existen)
├── infrastructure/
│   ├── agent/                   # contract loaders (sin cambios)
│   └── criteria/composition.py  # (verificar extractor cableado)
└── workers/
    └── criteria.py              # (sin cambios; job extraction.run existe)

contracts/
├── agent/tools/tool-contract-v2.json   # + propose_search_preference_update
├── agent/v3/intent-schema-v3.json      # refinamiento: + nueva tool
└── criteria/v1/preferences-vocabulary-v1.json  # NUEVO (feature contracts/ → repo contracts/)

scripts/
└── seed-local.py               # + seed de conceptos/extracción/observaciones

apps/web/src/
├── components/chat/proposal-card.tsx    # render diff de preferencia (si aplica)
└── lib/chat/types.ts                     # tipos del diff

tests/
├── unit/application/agent/tools/        # + traducción canónica, flujo tool
├── unit/agent/tools/                    # + tool preference
├── contract/                            # + contract tool v2, intent v3, vocabulario
├── unit/agent/                          # + graph v3 HITL preferencia
└── contract/                            # evals golden + casos de preferencia
```

**Structure Decision**: monolith modular existente; los cambios siguen la dirección agent → application → infrastructure ya establecida; sin módulos nuevos fuera de `application/agent/tools/preferences.py`.
