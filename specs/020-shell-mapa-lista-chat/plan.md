# Implementation Plan: Shell Umbral — mapa full-bleed + lista flotante + chat por radar

**Branch**: `020-shell-mapa-lista-chat` | **Date**: 2026-08-27 | **Spec**: [spec.md](./spec.md) (mirror de `docs/superpowers/specs/2026-08-27-umbral-shell-mapa-lista-chat.md`)

**Input**: Feature specification from `/specs/020-shell-mapa-lista-chat/spec.md`

## Summary

Instalar el shell de producto de 3 regiones push (nav radares 280px → rail 64px / main mapa full-bleed + lista flotante 320px + sheet detalle 380px / aside chat 400px) con estado `?listingId` shallow, pins Luz serena (forest/terracotta) sin cluster, `flyTo` 900ms auditado via tool `update_map_viewport`, señales urbanas reales desde snapshot SHA-256 + contrato versionado, y conversación scopeada por `search_profile_id`. Todo sobre tokens `--brand-*`, `next/font` Fraunces/DM Sans, landmarks a11y y datos reales estilo playground, con comparador y notifs proactivas fuera de alcance.

## Technical Context

**Language/Version**: Python `>=3.13,<3.14` (API/workers, no cambios), TypeScript `6` / React `19.2` / Next.js `16.2` (web), MapLibre `>=6.2`

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy 2, Alembic, LangGraph (orchestrator con tools explícitos), TanStack Query 5, shadcn/ui, Tailwind 4, `maplibre-gl`, `ai-elements`, `nuqs` (o `useSearchParams` nativo) para `?listingId`

**Storage**: Postgres + PostGIS + pgvector (radars/profiles/listings/explanations/snapshots urbanos existentes); object storage para snapshots; Redis para queue/cache; sin migración DB en este incremento (lectura de snapshots/contracts ya versionados)

**Testing**: pytest (no toca backend en este plan), Vitest 4 + Testing Library + jsdom (shell integration), Playwright + axe-core (a11y/contraste/reflow), harness `scripts/check-web.ps1` (lint/typecheck/vitest/playwright collection)

**Target Platform**: Web App Router Linux (standalone), dev Windows PowerShell

**Project Type**: Web application — `apps/web` (Next.js App Router) + `src/umbral` (API/application) ya existente; sin nuevo servicio

**Performance Goals**: Mapa full-bleed <100ms primera pintura sobre tiles cacheados; `flyTo` 900ms sin jank; lista 8 cards sin virtualización, scroll independiente; build `next build` sin aumento >150KB gz para nueva shell; a11y 0 violaciones serias/críticas

**Constraints** (de constitution + brand + grilling)
- Constitución I/II/III/IV/V: radar/product truth persistente, matching/scoring determinista versionado, dependencias inward UI→API→application→domain, cambios quirúrgicos + verificación obligatoria, linaje Bronze→Silver→Gold con evidencia/confianza
- Brand hard: bosque `#293F38` texto/primary, lino `#F4EFE6` fondo, terracotta `#DE6D4A` solo novedad (nunca destructive), arena `#D9C59F`, marfil `#FFFAF2`; Fraunces headings breves, DM Sans UI; zona ¼ símbolo; símbolo 16px; shadcn semánticos exclusivos
- Map: fork style playground desaturado con 4 brand hex, terracota solo pin selected, atribución solo `GlobalAttribution`, `attributionControl: false`, reduced-motion → `jumpTo`
- Estado: `?listingId` shallow (deeplink/back), hover ephemeral, viewport no persistido, espiral offset 12px si colisión <30px, sin cluster para ≤8
- Chat: 1:1 radar=session lazy, HITL/reasoning via ai-elements en stream, tool `update_map_viewport` sin mutar hard-filters, explicaciones citan evidencia/versión

**Scale/Scope**: 1 shell integrado, 3 regiones, 1 mapa, 1 lista max 8, 1 sheet detalle, 1 chat scopeado, ~6 nuevas componentes client + 1 server shell wrapper; reutiliza 70 tests existentes + ~5 nuevos shell tests; compatible con `/radar`, `/radar/new` (Dialog), `?filter` alias para shortlist/dismissed

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Persistent radar truth**: PASS. Cada radar = `search_profile` persistido; listings/matches/explanations/feedback/events ya persistentes; `?listingId` no crea objetos volátiles; chat crea session lazy pero no sustituye verdad producto
- **Auditable matching**: PASS. Hard filters/ranking/notifs siguen en código determinista versionado; LLM solo interpreta intención y emite tool `update_map_viewport` con `reason`; cada oportunidad conserva snapshot perfil/listing, scoring version, señal versión
- **Layer boundaries**: PASS. UI (shell/map/list/chat) → `lib/radar/client` + `api/radar/*` → `application/radar|urban|matching|scoring` → `domain/contracts`; `infrastructure` detrás de puertos; Agent tools explícitas, sin SQL libre
- **Data lineage and evidence**: PASS. Snapshots urbanos inmutables con SHA-256 importados Silver; primitivas 300/600 + señales urbanas con contrato versionado; incertidumbres mapeadas a `unknown` con `no sabemos` UI
- **Minimal verifiable scope**: PASS por fases abajo; no se rediseña ingesta, notifs proactivas, scoring, ni identity; cada tarea verifica con `vitest`/`typecheck`/`build`/`playwright` + grilling Q15-Q18 DONE.

Re-check post-Phase 1: PASS, sin excepciones → no se llena Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/020-shell-mapa-lista-chat/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── shell-contracts.md
│   ├── urban-signals-contract.md
│   └── map-viewport-tool.md
└── tasks.md             # Phase 2 output (NOT created by plan)
```

### Source Code (repository root)

```text
apps/web/
├── src/
│   ├── app/
│   │   ├── layout.tsx                # ya con fonts/tokens; añade shell landmarks
│   │   ├── globals.css               # tokens Luz serena
│   │   ├── (protected)/
│   │   │   └── radar/
│   │   │       ├── page.tsx          # lista radares → alimenta sidebar (reusa)
│   │   │       └── [id]/
│   │   │           ├── page.tsx      # se convierte en shell 3 paneles (main wrapper)
│   │   │           └── layout.tsx    # opcional shell layout por radar
│   │   └── api/radar/*               # ya existe; consume sin cambios
│   ├── components/
│   │   ├── brand/brand-logo.tsx      # ya existe
│   │   ├── radar/
│   │   │   ├── radar-sidebar.tsx     # nuevo: nav Radares (280→64, editable)
│   │   │   ├── radar-shell.tsx       # nuevo: orquestador 3 regiones + URL sync
│   │   │   ├── map/
│   │   │   │   ├── map-luz-serena.tsx       # fork geo-map con style desaturado
│   │   │   │   ├── opportunity-pins.tsx     # pins forest/terracotta + offset espiral
│   │   │   │   └── map-style-luz-serena.json# nuevo style o fork
│   │   │   ├── opportunities/
│   │   │   │   ├── floating-list.tsx        # sheet 320px lista curada max 8
│   │   │   │   └── opportunity-detail-sheet.tsx # 380px dentro main
│   │   │   └── chat/
│   │   │       └── radar-chat-panel.tsx     # wrapper sobre chat existente scopeado
│   │   ├── chat/*                    # ya existe (panel, message-list, proposal-card, ai-elements)
│   │   └── ui/*                      # shadcn (Button, Card, Sheet, Dialog, Tabs)
│   ├── lib/
│   │   ├── radar/client.ts           # ya existe
│   │   └── urban/                    # helpers contrato (opcional)
│   └── test/mocks/
│       ├── next-font-google.ts       # ya existe
│       └── maplibre-gl.ts            # mock isStyleLoaded/setPaintProperty/on/once
│
src/umbral/
├── application/
│   ├── radar/                        # solo consumo; sin cambios en este plan
│   ├── urban/                        # contrato + snapshot lectura
│   └── matching/scoring/             # sin cambios
└── api/routers/radar/*               # sin cambios salvo alias ?filter

tests/ (web)
├── src/app/(protected)/radar/shell.integration.test.tsx
├── src/components/radar/map-selection.test.tsx (opcional bajo mock)
└── e2e web-foundation.spec.ts extendido (axe + reflow)
```

**Structure Decision**: Single project monolith — se extiende `apps/web` existente; no se crean backend/apps nuevas, workers nuevos ni DB separada. El shell vive en `(protected)/radar/[id]` con componentes client bajo `components/radar/*` y reutiliza `lib/radar/client`, `components/chat/*`, `geo-map-*` helpers y `ui/*` shadcn.

## Complexity Tracking

No hay violaciones de constitución que justificar.
