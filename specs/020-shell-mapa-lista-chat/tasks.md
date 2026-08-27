# Tasks: Shell Umbral — mapa full-bleed + lista flotante + chat por radar

**Input**: Design documents from `/specs/020-shell-mapa-lista-chat/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/
**Tests/checks**: Include verification tasks for every behavioral change. Automated tests are preferred; when they are not practical yet, include contract, manual, or audit checks with expected outcomes.
**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure for shell

- [ ] T001 Create radar shell feature directories per plan in apps/web/src/components/radar and apps/web/src/components/radar/map in apps/web/src/components/radar/map/map-luz-serena.tsx
- [ ] T002 [P] Configure map style fork placeholder map-style-luz-serena.json in apps/web/src/components/radar/map/map-style-luz-serena.json
- [ ] T003 [P] Add MapLibre mock helpers for isStyleLoaded/setPaintProperty/once/on in apps/web/src/test/mocks/maplibre-gl.ts

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [ ] T004 Implement URL sync hook for ?listingId and ?filter with useSearchParams in apps/web/src/lib/radar/use-radar-selection.ts
- [ ] T005 [P] Implement spiral offset helper for pin collision <30px in apps/web/src/components/radar/map/pin-offset.ts
- [ ] T006 [P] Define shell contracts types for Radar/Oportunidad/Pin/Viewport in apps/web/src/lib/radar/shell-contracts.ts
- [ ] T007 Setup shell landmarks base (nav/main/aside) and skip-link preservation in apps/web/src/app/(protected)/radar/[id]/layout.tsx
- [ ] T008 [P] Add audit field helper for scoring_version/signal_version/snapshot hash display in apps/web/src/lib/urban/signal-meta.ts
- [ ] T009 Configure reduced-motion helper for flyTo vs jumpTo in apps/web/src/lib/map/motion.ts

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

## Phase 3: User Story 1 — Sidebar Radares + Shell 3 regiones (Priority: P1) — MVP

**Goal**: Sidebar izquierda lista radares 1:1 con sesión chat, nombre editable, 3 regiones push (280/flex/400) con colapso 1280/1024 y drawers <1024. URL `/radar/[id]` deeplinks.

**Independent Test**: Render `RadarShell` con 2 radares mocked; sidebar muestra `nav[Radares]` con items, seleccionar cambia `?listingId` no recargando, rail 64 colapsado muestra iconos; Playwright reflow 320/768/1440 sin overflow.

### Tests for User Story 1

- [ ] T010 [P] [US1] Shell integration test for sidebar navigation in apps/web/src/app/(protected)/radar/shell.integration.test.tsx
- [ ] T011 [P] [US1] Unit test for radar selection URL hook in apps/web/src/lib/radar/use-radar-selection.test.ts

### Implementation for User Story 1

- [ ] T012 [P] [US1] Create RadarSidebar component with editable name and collapse to rail in apps/web/src/components/radar/radar-sidebar.tsx
- [ ] T013 [US1] Create RadarShell orchestrator with 3 regions push/overlay/drawer breakpoints in apps/web/src/components/radar/radar-shell.tsx
- [ ] T014 [US1] Implement /radar redirect to / with sidebar and /radar/new as Dialog in apps/web/src/app/(protected)/radar/page.tsx
- [ ] T015 [US1] Wire radar/[id]/page.tsx to use RadarShell with lazy chat session in apps/web/src/app/(protected)/radar/[id]/page.tsx
- [ ] T016 [US1] Add responsive Tabs Mapa|Lista|Chat + drawer hamburger for <1024 in apps/web/src/components/radar/radar-shell.tsx

**Checkpoint**: At this point, User Story 1 should be fully functional and testable independently — radares navegables sin mapa data

## Phase 4: User Story 2 — Mapa Luz Serena + Lista flotante sincronizada (Priority: P1)

**Goal**: Mapa full-bleed desaturado Luz serena ocupa main; lista flotante izq 320px scroll muestra max 8 curadas filtradas por ?filter, hover→pin highlight, click→?listingId + flyTo zoom 16, pins terracota selected / bosque hover, espiral offset sin cluster.

**Independent Test**: Con 8 oportunidades mocked, hover card escala pin + ring, click cambia URL y llama flyTo con reason, ?filter=saved muestra solo guardadas, axe 0 serias.

### Tests for User Story 2

- [ ] T017 [P] [US2] Integration test for floating list hover and filter tabs in apps/web/src/components/radar/opportunities/floating-list.test.tsx
- [ ] T018 [P] [US2] Unit test for pin offset spiral helper in apps/web/src/components/radar/map/pin-offset.test.ts
- [ ] T019 [P] [US2] Integration test for map pin selection and flyTo in apps/web/src/components/radar/map/map-luz-serena.test.tsx

### Implementation for User Story 2

- [ ] T020 [P] [US2] Fork map style to Luz Serena desaturado (lino/bosque/arena/marfil + terracotta pins) in apps/web/src/components/radar/map/map-style-luz-serena.json
- [ ] T021 [P] [US2] Implement MapLuzSerena wrapper with attributionControl false and reduced-motion guard in apps/web/src/components/radar/map/map-luz-serena.tsx
- [ ] T022 [US2] Implement OpportunityPins layer with forest default, terracotta selected, hover ring and spiral offset in apps/web/src/components/radar/map/opportunity-pins.tsx
- [ ] T023 [US2] Implement FloatingList sheet 320px with All|Guardadas|Descartadas tabs, max 8, aria-selected, scrollIntoView in apps/web/src/components/radar/opportunities/floating-list.tsx
- [ ] T024 [US2] Integrate FloatingList + MapLuzSerena + Pins via ?listingId sync and hover state in apps/web/src/components/radar/radar-shell.tsx
- [ ] T025 [US2] Add empty state (Skeleton 3 cards + Spinner role=status) and calma CTA Ajustar el radar in apps/web/src/components/radar/opportunities/floating-list.tsx

**Checkpoint**: At this point, User Stories 1 AND 2 should both work independently — mapa+lista curada navegable

## Phase 5: User Story 3 — Sheet Detalle + Señales Urbanas reales (Priority: P1)

**Goal**: Sheet detalle 380px dentro de main (no modal) muestra foto→por qué encaja→concesiones→incertidumbres (Alert)→señales urbanas con snapshot hash→acciones Ver/Guardar/Descartar/Consultar + feedback soft/hard por concepto, foco a h2 y Esc retorno.

**Independent Test**: Click card abre sheet con landmarks correctos, foco en h2, Esc limpia ?listingId y devuelve foco, señales reales al menos transporte + unknown fallback con "no sabemos", contrast AA.

### Tests for User Story 3

- [ ] T026 [P] [US3] Integration test for detail sheet focus and Esc handling in apps/web/src/components/radar/opportunities/opportunity-detail-sheet.test.tsx
- [ ] T027 [P] [US3] Unit test for signal meta display (sha256/date/unknown) in apps/web/src/lib/urban/signal-meta.test.ts

### Implementation for User Story 3

- [ ] T028 [P] [US3] Create OpportunityDetailSheet with hierarchy foto/por qué/concesiones/incertidumbre/señales/acciones in apps/web/src/components/radar/opportunities/opportunity-detail-sheet.tsx
- [ ] T029 [US3] Wire detail sheet to fetch listing + explanations + urban signals (count_300/600, distance_nearest) via lib/radar/client in apps/web/src/components/radar/opportunities/opportunity-detail-sheet.tsx
- [ ] T030 [US3] Implement feedback inline per concepto with soft→hard elevation and HITL confirm in apps/web/src/components/radar/opportunities/opportunity-detail-sheet.tsx
- [ ] T031 [US3] Highlight urban primitives on map via scheduleCategoryPaint/scheduleSelectedFeaturePaint on selection in apps/web/src/components/radar/map/map-luz-serena.tsx
- [ ] T032 [US3] Handle signal unknown fallback with Alert "no sabemos — punto para consultar" in apps/web/src/components/radar/opportunities/opportunity-detail-sheet.tsx

**Checkpoint**: All user stories should now be independently functional — detalle auditable con datos reales

## Phase 6: User Story 4 — Chat por Radar + Tool viewport (Priority: P1)

**Goal**: Aside derecho chat 100% scopeado por search_profile_id, lazy session, reasoning/HITL via ai-elements, chips bienvenida; tool update_map_viewport {center,zoom,reason} anima map flyTo 900ms (jumpTo si reduced-motion) sin mutar hard-filters, auditable en stream.

**Independent Test**: /radar/[id] carga chat history scopeado, welcome + chips disparan mensaje, tool mueve mapa y muestra reason, no cambia profile filters.

### Tests for User Story 4

- [ ] T033 [P] [US4] Integration test for radar-scoped chat with lazy session in apps/web/src/components/radar/chat/radar-chat-panel.test.tsx
- [ ] T034 [P] [US4] Unit test for update_map_viewport tool validation and reduced-motion guard in apps/web/src/lib/map/motion.test.ts

### Implementation for User Story 4

- [ ] T035 [P] [US4] Create RadarChatPanel wrapper scoped to search_profile_id with resume and ai-elements blocks in apps/web/src/components/radar/chat/radar-chat-panel.tsx
- [ ] T036 [US4] Implement update_map_viewport tool contract handling and emit map:flyTo with reason in apps/web/src/components/radar/radar-shell.tsx
- [ ] T037 [US4] Add welcome state with descriptor + 3 chips and stream-status reasoning display in apps/web/src/components/radar/chat/radar-chat-panel.tsx
- [ ] T038 [US4] Integrate chat → map coupling (tool does not mutate search_profile, auditable) in apps/web/src/components/radar/radar-shell.tsx

**Checkpoint**: At this point, User Stories 1-4 should all work — shell completo navegable con chat situado

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories + migration legacy + a11y perf

- [ ] T039 [P] Add legacy aliases for shortlist/dismissed as ?filter saved/dismissed and Dialog for /radar/new in apps/web/src/app/(protected)/radar/[id]/page.tsx
- [ ] T040 [P] Ensure landmarks nav[Radares]/main[Mapa de oportunidades]/aside[Conversación] + skip-link + focus management across shell in apps/web/src/components/radar/radar-shell.tsx
- [ ] T041 [P] Apply brand constraints: terracotta never destructive, Fraunces only headings, shadcn semantic classes, zone ¼ symbol in apps/web/src/app/globals.css
- [ ] T042 [P] Add bell mock with badge linking to /notifications legacy (no push) in apps/web/src/components/radar/radar-shell.tsx
- [ ] T043 Extend web-foundation.spec.ts for axe 0 serious on shell light/dark and reduced-motion flyTo check in apps/web/e2e/web-foundation.spec.ts
- [ ] T044 Run quickstart validation and ensure typecheck/lint/build pass in specs/020-shell-mapa-lista-chat/quickstart.md
- [ ] T045 [P] Update docs/brand/visual-foundations.md with shell usage examples if needed in docs/brand/visual-foundations.md

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (P1 → P1 → P1 → P1)
- **Polish (Final Phase)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1) — Sidebar+Shell**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P1) — Mapa+Lista**: Can start after Foundational - Integrates with US1 shell but independently testable (mocked radares)
- **User Story 3 (P1) — Detalle+Señales**: Depends on US2 map pins/selection — needs ?listingId sync from US2, otherwise independently testable with mocked selection
- **User Story 4 (P1) — Chat+Tool**: Can start after Foundational - Depends on US1 sidebar selectedId but testable with mocked radarId; integrates with US2 viewport tool

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models/contracts before services
- Services before components
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational completes, US1 and US4 can start in parallel (different files); US2 and US3 share map files but pins vs sheet are separate
- All tests for a user story marked [P] can run in parallel
- Pin helpers and style fork can run in parallel within US2

## Parallel Example: User Story 2

```bash
# Launch all tests for User Story 2 together:
Task: "Integration test for floating list hover and filter tabs in apps/web/src/components/radar/opportunities/floating-list.test.tsx"
Task: "Unit test for pin offset spiral helper in apps/web/src/components/radar/map/pin-offset.test.ts"
Task: "Integration test for map pin selection and flyTo in apps/web/src/components/radar/map/map-luz-serena.test.tsx"

# Launch all components for User Story 2 together:
Task: "Fork map style to Luz Serena desaturado in apps/web/src/components/radar/map/map-style-luz-serena.json"
Task: "Implement MapLuzSerena wrapper in apps/web/src/components/radar/map/map-luz-serena.tsx"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test User Story 1 independently via shell.integration.test + Playwright reflow
5. Deploy/demo if ready — sidebar + shell sin datos urbanos aún útil para navegación radares

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP: navegación radares)
3. Add User Story 2 → Test independently → Deploy/Demo (+ mapa+lista 8 curadas)
4. Add User Story 3 → Test independently → Deploy/Demo (+ detalle auditable)
5. Add User Story 4 → Test independently → Deploy/Demo (+ chat situado)
6. Each story adds value without breaking previous stories; use ?filter aliases to keep e2e green

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (sidebar+shell)
   - Developer B: User Story 2 (mapa+lista) — depends lightly on shell but can mock
   - Developer C: User Story 4 (chat+tool) — parallel to map
3. Developer D picks US3 after US2 pins ready; Polish together

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- Constitution: radar truth persistent, matching deterministic, tools explicit, data lineage preserved, scope minimal verificable

