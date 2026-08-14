# Implementation Plan: Copiloto conversacional de búsqueda

**Branch**: `016-conversational-search-copilot` | **Date**: 2026-08-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/016-conversational-search-copilot/spec.md`

## Summary

Reemplazar el flujo de formulario conversacional por un copiloto que crea radares parciales, procesa actos múltiples, conserva cualquier deseo por radar y solo convierte en scoring aquello que tiene una vinculación evaluable. La implementación agrega un módulo profundo de preferencias, un orquestador de turnos, contratos de agente v4, scoring semántico acotado y evals de trayectorias; las mutaciones siguen pasando por servicios explícitos y el ranking permanece puro, determinista y versionado.

## Technical Context

**Language/Version**: Python `>=3.13,<3.14`; TypeScript `6`; React `19.2`; Next.js `16.2`

**Primary Dependencies**: FastAPI `>=0.138`, Pydantic `2.13`, SQLAlchemy `2.0.51`, Alembic, LangGraph `1.2.10`, pgvector, shadcn/ui, Tailwind CSS `4`, TanStack Query

**Storage**: PostgreSQL con PostGIS y pgvector; snapshots/versiones y eventos auditables existentes

**Testing**: pytest, Vitest, Testing Library, Playwright, contracts JSON versionados, harness `scripts/check.ps1`

**Target Platform**: API/workers Linux y navegador evergreen; desarrollo Windows compatible con PowerShell

**Project Type**: Aplicación web con backend Python, frontend Next.js y workers asíncronos

**Performance Goals**: primera señal visible `<1s`; p95 de respuesta conversacional normal `<5s`; refresh largo no bloqueante

**Constraints**: 100% invariantes críticos; 95% trayectorias global; ninguna familia `<90%`; cero ranking generativo; semántica solo suave con peso `<=0.10`; estado durable antes del refresh

**Scale/Scope**: beta privada CABA/alquileres; múltiples radares por usuario; catálogo compartido finito y expresiones no acotadas por radar

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Dirección de dependencias**: PASS. UI -> API -> `ConversationTurnService`/servicios de aplicación -> dominio; adapters implementan puertos.
- **Agent Orchestrator con tools explícitas**: PASS. El modelo produce actos; política determinista valida y servicios explícitos mutan.
- **Scoring puro, determinista y versionado**: PASS. La similitud usa embeddings congelados y el motor recibe señales, sin I/O ni ranking LLM.
- **Persistencia fuera del chat**: PASS. Radares, expresiones, bindings, facts, compilaciones y evaluaciones son objetos persistentes.
- **Evidencia y explicaciones**: PASS. Cada criterio compilado conserva binding, versiones y refs de embeddings/observaciones.
- **Embeddings no reemplazan hard filters**: PASS. Bindings semánticos tienen `mode=soft` y peso máximo `0.10`.
- **Cambios quirúrgicos**: PASS por fases. No se rediseñan ingestión, identidad o notificaciones; se extienden seams existentes.
- **Equidad**: PASS. La política bloquea operacionalización antes de binding/compilación y conserva una limitación explícita.

Revisión posterior a diseño: PASS, sin excepciones que requieran Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/016-conversational-search-copilot/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── chat-copilot-contracts-v1.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
src/umbral/
├── application/
│   ├── preferences/        # expresiones, bindings, autoridad y compilación
│   ├── conversation/       # contexto, planificación y aplicación de turnos
│   ├── radar/              # radares parciales, runs y coalescing
│   ├── scoring/            # señales semánticas y diagnósticos puros
│   └── agent_evals/        # trayectorias v2 y gates
├── agent/                  # graph/state/interpretation v4
├── api/routers/            # chat y vistas de preferencias
└── infrastructure/
    ├── db/                 # modelos y repositorios
    └── agent/              # composición y gateway estructurado

apps/web/src/
├── app/(protected)/radar/new/
├── components/chat/
├── components/radar/
└── lib/chat/

contracts/
├── agent/v4/
├── agent-evals/v2/
├── preferences/v1/
└── scoring/v2/

alembic/versions/0016_conversational_search_copilot.py

tests/
├── contract/
├── unit/application/{preferences,conversation,radar,scoring,agent_evals}/
├── integration/{chat,api,preferences,scoring}/
└── migrations/test_0016_conversational_search_copilot.py
```

**Structure Decision**: conservar el monorepo y las capas actuales. Los dos módulos nuevos se ubican en aplicación porque encapsulan reglas de negocio; FastAPI, LangGraph, SQLAlchemy y el modelo permanecen adapters/orquestación externa.

## Complexity Tracking

No hay violaciones de constitución que justificar.
