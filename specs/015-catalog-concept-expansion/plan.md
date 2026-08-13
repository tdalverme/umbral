# Implementation Plan: Expansión del catálogo de conceptos (Fase 3)

**Branch**: `015-catalog-concept-expansion` | **Date**: 2026-08-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/015-catalog-concept-expansion/spec.md`

## Summary

Hacer que agregar un concepto nuevo sea "solo datos + golden" para los tres tipos de concepto (regla, modelo cualitativo, señal urbana). Para eso se cierran tres brechas de infraestructura (weight del fact en la compilación, canal urban → observaciones, golden de extracción) y se validan con dos casos completos: "moderno" (cualitativo) y "proximidad_cafes" (urbano), más "acceso_transporte" (replica del urbano). El chat adopta los conceptos nuevos solo con vocabulario.

## Technical Context

**Language/Version**: Python 3.13; TypeScript 5.x (web, sin cambios previstos)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 + Alembic, LangGraph (sin cambios de topología)

**Storage**: PostgreSQL 17 con PostGIS (geometría de señales ya existe) y pgvector (sin uso nuevo)

**Testing**: pytest (unit/contract/integration), ruff, mypy estricto, harness `scripts/check.ps1`

**Target Platform**: Linux server (API + workers), navegador

**Project Type**: monolith modular (monorepo)

**Performance Goals**: consolidación urbana en el worker de criteria (batch); sin llamadas al modelo para conceptos urbanos

**Constraints**: 0 cambios en el engine por concepto nuevo; proxy versionado y explícito; golden gatea la publicación; 0 LLM en decisiones de ranking

**Scale/Scope**: beta CABA; tres conceptos nuevos (moderno, proximidad_cafes, acceso_transporte); subte D fuera de alcance

## Constitution Check

| Gate | Regla | Cumple |
|------|-------|--------|
| I. Persistent Radar | Preferencias y observaciones persistentes versionadas | Sí |
| II. Auditable Deterministic | Proxies versionados, scoring determinístico, golden de calidad | Sí |
| III. Layered | Consolidación en aplicación; engine puro; 0 infra en dominio | Sí |
| IV. Minimal Verifiable | Reuso de numeric_range/evaluadores/invalidación; golden por concepto | Sí |
| V. Data Lineage | Observaciones urbanas con evidencia citando señales + versión | Sí |

## Project Structure

```text
src/umbral/
├── application/
│   ├── criteria/
│   │   ├── contracts.py        # CompiledCriterion.weight
│   │   ├── compile.py          # facts → criterio con weight + params (ya con polarity)
│   │   ├── service.py          # consolidación urban (source urban) en _extract_concept
│   │   └── extractor.py        # gate de golden (evaluar casos vs extracción)
│   └── scoring/
│       └── engine.py           # usar weight del criterio compilado con fallback al policy
├── infrastructure/
│   └── criteria/
│       └── contract_loader.py  # + loader del golden
contracts/
├── criteria/v1/
│   ├── concepts-seed-v1.json   # + moderno, proximidad_cafes, acceso_transporte
│   ├── extraction-v1.json      # + entradas urban
│   └── extraction-goldens-v1.json  # NUEVO
├── agent/v3/intent-schema-v3.json      # (sin cambios; refinamiento ya cubre)
└── criteria/v1/preferences-vocabulary-v1.json  # + moderno, cerca de cafés, transporte
tests/
├── unit/application/criteria/  # consolidación urban, weight en compilación
├── unit/application/scoring/   # weight del hecho en el ranking
├── contract/                   # golden de extracción, contracts de los conceptos nuevos
├── fixtures/criteria/          # golden de moderno/cafés
└── contract/                   # evals golden del chat (frases nuevas)
scripts/
└── check-criteria.ps1          # + gate de golden de extracción
```

## Fases de implementación

1. **Fundación**: weight en CompiledCriterion (contrato + compile + engine + tests); canal urban (consolidación en criteria service + loader + tests); golden de extracción (contrato + gate + harness).
2. **Caso "moderno"**: catálogo + schema + vocabulario + golden + evals chat + validación end-to-end.
3. **Caso "proximidad_cafes"**: catálogo urbano + proxy + consolidación + golden + evals chat + validación end-to-end (ranking con señales reales o seed de señales demo).
4. **Caso "acceso_transporte"**: réplica del ciclo urbano.
5. **Polish**: quickstart con evidencia, evals golden del chat, harness completo.

## Riesgos

- El golden sintético inicial solo gatea la mecánica, no la calidad real: calibrar con uso (feedback, explicaciones vistas).
- El proxy de cafés no captura calidad percibida: se declara en la explicación.
- Costo de modelo de los cualitativos: monitorear en la extracción.
