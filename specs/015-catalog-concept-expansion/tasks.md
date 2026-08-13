# Tasks: Expansión del catálogo de conceptos (Fase 3)

**Input**: Design documents from `/specs/015-catalog-concept-expansion/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Organization**: fundación (bloquea todo) → caso cualitativo → caso urbano → réplica urbana → polish.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Foundational — G1 weight del hecho en la compilación (US3)

- [ ] T001 [P] [US3] Contract test: `compilation-v1.json` schema del criterio incluye `weight` opcional; `CompiledCriterion` en `src/umbral/application/criteria/contracts.py` agrega `weight: float | None`
- [ ] T002 [P] [US3] `src/umbral/application/criteria/compile.py`: `_facts_to_criteria` setea `weight=fact.weight` (ya setea params con polarity); edits quedan con weight None
- [ ] T003 [US3] `src/umbral/application/scoring/engine.py`: el override de params de un fact usa también `weight` del criterio compilado cuando no es None (fallback al policy)
- [ ] T004 [US3] Unit tests: fact con peso propio de un concepto fuera del policy mueve el ranking en la dirección de la polarity en `tests/unit/application/scoring/`

## Phase 2: Foundational — G2 canal urbano (US2/US4)

- [ ] T005 [P] [US2] `src/umbral/application/criteria/contracts.py`: `ExtractionConcept`/loader acepta `source: "urban"` con `signal_type` y `proxy` (radio_m, min) en `extraction-v1.json`
- [ ] T006 [P] [US2] `src/umbral/application/criteria/service.py`: `_extract_concept` branch `source == "urban"` → `_extract_urban_observation`: consulta `urban_signals.list_for_listing`, filtra por `signal_type` y radio (haversine contra geometry del listing), produce `ListingObservation(source="urban", value=count, score=min(count/proxy.min, 1.0), evidence=señales citadas)`
- [ ] T007 [US2] `_ensure_extraction_version` para urban: kind `rule`, version derivada del proxy (`urban-r{radio}-m{min}`) para invalidación selectiva al cambiar el proxy
- [ ] T008 [P] [US2] Unit tests de la consolidación (señales en radio, fuera de radio, sin señales → count 0, proxy aplicado, evidencia con signal_id + algorithm_version) en `tests/unit/application/criteria/`

## Phase 3: Foundational — G3 golden de extracción (US5)

- [ ] T009 [P] [US5] Contrato `contracts/criteria/v1/extraction-goldens-v1.json` (casos input/expected + threshold accuracy) + loader en `src/umbral/infrastructure/criteria/contract_loader.py`
- [ ] T010 [P] [US5] Función pura `evaluate_extraction_golden` (accuracy vs threshold) en `src/umbral/application/criteria/extractor.py` (reglas: corre `run_rule`; modelos: smoke estructural — schema cubre los valores esperados del golden, documentado)
- [ ] T011 [US5] Contract test del golden + gate en `scripts/check-criteria.ps1` (path `tests/contract/test_extraction_goldens.py`)

## Phase 4: Caso cualitativo "moderno" (US1) 🎯

- [ ] T012 [P] [US1] `concepts-seed-v1.json` + `extraction-v1.json`: concepto `moderno` (semantic_feature, aliases, compute_policy unknown exclude, schema enum `clasico|renovado|moderno` + evidence + confidence)
- [ ] T013 [P] [US1] Golden de extracción para `moderno` (casos por valor del enum + casos ambiguos) en `extraction-goldens-v1.json`
- [ ] T014 [P] [US1] Vocabulario del chat: "moderno", "renovado", "actual" → moderno/positive en `preferences-vocabulary-v1.json` + ejemplo en el intent compiler
- [ ] T015 [US1] Tests: contract (seed parse), unit (score del enum para moderno), golden pasa; validación end-to-end local (seed → extracción → chat "quiero algo moderno" → fact → ranking)

## Phase 5: Caso urbano "proximidad_cafes" (US2) 🎯

- [ ] T016 [P] [US2] `concepts-seed-v1.json` + `extraction-v1.json`: concepto `proximidad_cafes` (numeric_range, params_schema `{min: 1}`, source urban, signal_type `cafe`, proxy `{radio_m: 500, min: 1}`)
- [ ] T017 [P] [US2] Golden de extracción para `proximidad_cafes` (casos con señales en/fuera de radio) — smoke sobre la consolidación
- [ ] T018 [P] [US2] Vocabulario: "cerca de cafes", "con cafes cerca" → proximidad_cafes/positive
- [ ] T019 [US2] `scripts/seed-local.py`: sembrar señales urbanas demo (cafe/transport con geometría y algorithm_version) + habilitar `urban_context_enabled` en el seed; tests del seed; validación end-to-end (extracción urban → chat "quiero un depto cerca de cafés" → fact → ranking y explicación citan señales)

## Phase 6: Réplica urbana "acceso_transporte" (US4)

- [ ] T020 [P] [US4] `concepts-seed-v1.json` + `extraction-v1.json`: `acceso_transporte` (numeric_range, source urban, signal_type `transport`, proxy)
- [ ] T021 [P] [US4] Golden + vocabulario ("buen transporte", "bien conectado" → acceso_transporte/positive)
- [ ] T022 [US4] Tests y validación end-to-end del ciclo urbano réplica

## Phase 7: Polish

- [ ] T023 [P] Evals golden del chat: casos "quiero algo moderno" y "quiero un depto cerca de cafés" en `conversations-golden-v1.json` (familia preferences)
- [ ] T024 [P] `specs/015-catalog-concept-expansion/quickstart.md` con evidencia real de la validación (ranking con moderno/cafés)
- [ ] T025 Validación completa: ruff, mypy, pytest (unit/contract/architecture), harness `scripts/check.ps1`, web lint/typecheck

## Dependencies & Execution Order

- Phase 1-3 (fundación): independientes entre sí, bloquean las Fases 4-6
- Phase 4 (moderno): después de G1+G3
- Phase 5-6 (urbanos): después de G2+G3
- Phase 7: al final

## Notas

- El proxy vive en `extraction-v1.json` (no en params_schema del concepto, que valida contra allowed_params del matcher).
- El golden de modelos es smoke estructural (el harness no llama al modelo); el de reglas corre de verdad.
- 0 cambios en el engine por concepto nuevo (regla de oro del spec).
