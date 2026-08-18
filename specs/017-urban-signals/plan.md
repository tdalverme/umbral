# Implementation Plan: Señales urbanas declarativas

**Branch**: `017-urban-signals` | **Date**: 2026-08-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/017-urban-signals/spec.md` + contrato JSON concreto solicitado durante el plan.

## Summary

Rediseñar el contexto urbano con un contrato declarativo y versionado (tags OSM → categorías, primitivas, señales base y compuestas, normalización por barrio, confidence declarada). Un worker de ops importa un snapshot de OpenStreetMap (descarga externa → object storage → import), el batch computa señales por listing, normaliza por barrio y escribe observaciones urbanas que el scoring consume sin cambios. Los concepts urbanos migran de `proxy` a `signal_ref` con un matcher nuevo `signal_score`.

## Technical Context

**Language/Version**: Python `>=3.13,<3.14`; TypeScript `6`; React `19.2`; Next.js `16.2`

**Primary Dependencies**: FastAPI `>=0.138`, Pydantic `2.13`, SQLAlchemy `2.0.51`, Alembic, osmium, GeoAlchemy2, PostGIS

**Storage**: PostgreSQL con PostGIS; object storage para snapshots; observaciones versionadas existentes

**Testing**: pytest, contracts JSON versionados, harness `scripts/check.ps1`

**Target Platform**: API/workers Linux y navegador evergreen; desarrollo Windows compatible con PowerShell

**Project Type**: Aplicación web con backend Python, frontend Next.js y workers asíncronos

**Performance Goals**: recálculo batch de señales para todos los listings de CABA sin bloquear chat ni scoring; atribución visible sin afectar el rendimiento

**Constraints**: contrato versionado como un todo; señales factuales puras; scoring sin cambios; normalización por barrio con fallback global; desconocimiento explícito; ODbL con atribución global

**Scale/Scope**: beta privada CABA/alquileres; un snapshot urbano por vez; señales por listing

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Dirección de dependencias**: PASS. El contrato urbano y el calculator son dominio puro; el worker de ops y los adapters implementan puertos.
- **Scoring puro, determinista y versionado**: PASS. El scoring no cambia; consume observaciones versionadas con matcher `signal_score`.
- **Persistencia fuera del chat**: PASS. Señales, observaciones, snapshots y estadísticas son objetos persistentes.
- **Evidencia y explicaciones**: PASS. Cada observación cita crudo, normalizado, confidence, contrato y snapshot.
- **Datos abiertos licenciados**: PASS. Atribución ODbL declarada en el contrato y visible en superficie global.
- **Desconocimiento honesto**: PASS. Missing explícito, nunca un valor medio.
- **Cambios quirúrgicos**: PASS por fases. No se rediseñan ingestión, identidad ni notificaciones.
- **Equidad**: PASS. La normalización por barrio mitiga el sesgo de cobertura de OSM sin inventar datos.

Revisión posterior a diseño: PASS, sin excepciones que requieran Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/017-urban-signals/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── urban-contract-v1.json
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
src/umbral/
├── application/urban/        # contrato, calculator, normalización (dominio puro)
├── api/routers/              # atribución global y vistas de señales
├── workers/urban.py          # worker de import y batch
├── ops/import_urban.py       # comando de ops: descarga → object storage → import
└── infrastructure/
    ├── db/models/            # urban_contracts, snapshots, categorías, primitivas, señales, stats
    ├── db/repositories/      # repos urbanos + migración de concepts a signal_ref
    └── urban/                # adapters de import osmium, contract loader, calculator runner
```

```text
contracts/urban/v1/urban-contract-v1.json
alembic/versions/0017_urban_signals.py

tests/
├── contract/test_urban_contract.py
├── unit/application/urban/
├── integration/urban/
└── integration/agent_evals/test_trajectories_v2.py  # caso puente
```

**Structure Decision**: el módulo `application/urban` encapsula contrato + calculator + normalización como dominio puro; los adapters de import y repos viven en infraestructura; el worker y el comando de ops son la superficie operativa.

## Complexity Tracking

No hay violaciones de constitución que justificar.
