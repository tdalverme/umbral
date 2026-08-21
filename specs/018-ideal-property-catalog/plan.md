# Implementation Plan: Catalogo del inmueble ideal con fuerza por usuario

**Directory**: `specs/018-ideal-property-catalog` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/018-ideal-property-catalog/spec.md`

## Summary

Expandir el catalogo de conceptos (vivienda + entorno) que la persona puede expresar al describir su inmueble ideal, y completar el seam hard/soft para que cualquier criterio estructurado pueda ser soft (ordena) o hard (excluye) por usuario, con confirmacion y trazabilidad. La implementacion agrega `concepts-v2` y `urban-contract-v2`, reglas de extraccion deterministas, senales urbanas nuevas por contrato, la propagacion de `mode`->`soft_to_hard` en la compilacion y la exclusion por mismatch en el engine, y la medicion de la tasa de mapeo conversacional con trayectorias.

## Technical Context

**Language/Version**: Python `>=3.13,<3.14`; TypeScript `6`; React `19.2`; Next.js `16.2`

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy 2, Alembic, LangGraph, PostgreSQL/PostGIS/pgvector; edge en cero

**Storage**: PostgreSQL con PostGIS y pgvector; contracts versionados y eventos auditables existentes

**Testing**: pytest, contracts JSON versionados, tests de conformance, harness `scripts/check.ps1`

**Target Platform**: API/workers Linux; desarrollo Windows con PowerShell

**Constraints** (de spec y constitucion)

- Orden final, filtros duros y notificaciones deterministas y versionados (Constitucion II).
- Dependencias hacia adentro; el dominio no importa FastAPI/DB/LLM/UI (Constitucion III).
- Cambios quirurgicos; minimo codigo que resuelve el pedido (Constitucion IV).
- Semantica siempre soft con peso `<=0.10`; nunca un hard semantico (Constitucion II, FR-009).
- `bedrooms` ya normalizado; agregar a `allowed_input_fields` sin migracion de esquema.
- `health`/`green_space` ya existen en el contrato urbano; las senales nuevas van en `urban-contract-v2` (JSON).
- El hard se aplica por radar (profile), no global.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Direccion de dependencias**: PASS. Los cambios estan en `application/` (reglas, compilacion, engine) con adapters en `infrastructure/`; el dominio no gana dependencias externas.
- **Agent Orchestrator con tools explicitas**: PASS. La deteccion de fuerza la produce el copiloto como propuesta; la confirmacion y la aplicacion pasan por servicios y el engine determinista.
- **Scoring puro, determinista y versionado**: PASS. La nueva exclusion por `soft_to_hard` es un cambio puro en `engine.py`/`evaluators.py`; se cubre con tests y golden dataset.
- **Persistencia fuera del chat**: PASS. Hechos, bindings, compilaciones, observaciones y eventos de elevacion son objetos persistentes.
- **Evidencia y explicaciones**: PASS. Cada observacion nueva conserva evidencia/fragmento, y las explicaciones declaran el alcance y la confianza.
- **Embeddings no reemplazan hard filters**: PASS. Solo los conceptos estructurados pueden ser hard; los semantico siguen soft-capped.
- **Cambios quirurgicos**: PASS por fases. No se rediseña ingesta, notificaciones ni identity; se extienden los seams ya existentes (contracts, rules, engine, goldens).
- **Equidad**: PASS. El umbral de las senales y la exclusion por hard se declaran y se auditan; el aprender nunca genera hard.

Revisión posterior a diseño: PASS, sin excepciones que requieran Complexity Tracking.

## Fases

1. **Phase 1**: Catalogo de conceptos de vivienda (`concepts-v2` + reglas deterministas + modelo difuso + vocabulary).
2. **Phase 2**: Contrato urbano v2 con las 5 senales nuevas (escuela, deporte, cultura, bici, salud) + concepts/signal_ref + recomputo.
3. **Phase 3**: Mecanismo hard/soft por usuario (produccion de `mode`, compilacion `soft_to_hard`, exclusion en engine, golden dataset v2, eventos, diagnostics).
4. **Phase 4**: Trayectorias (medicion de mapeo), conformance, harness, docs y CONTEXT.

## Project Structure

```text
specs/018-ideal-property-catalog/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── catalog-hardsoft-contracts.md
├── research/research.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
src/umbral/
├── application/
│   ├── criteria/
│   │   ├── rules.py                 # reglas nuevas deterministas
│   │   └── compile.py               # propagacion mode->soft_to_hard
│   ├── preferences/                 # producer de mode hard + confirmacion
│   ├── scoring/
│   │   ├── engine.py                # exclusion por soft_to_hard en mismatch
│   │   └── evaluators.py            # umbral para signal_score hard
│   └── radar/
│       ├── hard_filters.py          # allowlist/protocol de criteria hard
│       └── diagnostics.py           # identificar criterio responsable del vacio
├── agent/                           # interpretacion de fuerza "si o si"/"plus"
├── infrastructure/
│   ├── criteria/contract_loader.py  # paths a contracts v2
│   └── urban/composition.py         # signal_ref -> conceptos v2
contracts/
├── criteria/v2/concepts-seed-v2.json
├── criteria/v2/extraction-v2.json
└── urban/v2/urban-contract-v2.json
alembic/versions/0018_hard_soft_catalog.py
tests/
├── contract/
├── unit/application/{criteria,scoring,preferences,radar}/
└── integration/
```

## Complexity Tracking

No hay violaciones de constitucion que justificar.