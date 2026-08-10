# Tasks: Evals, costos y operacion del agente

**Input**: Design documents from `specs/012-graph-evals-ops/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md),
[research.md](./research.md), [data-model.md](./data-model.md),
[contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests/checks**: El plan fija slices test-first ("each behavioral slice starts
with the failing contract/unit test named here"). En cada fase se escriben
primero los tests indicados y se confirma que fallan por la conducta ausente
antes de implementar.

**Organization**: Las tareas se agrupan por historia de `spec.md` conservando
los slices del plan (Phase A..G). Setup publica los contratos
`agent-evals/v1` (golden dataset, releases, price table), los 3 eventos de
registry y los settings `AGENT_EVALS_*`/`AGENT_BUDGET_*`/`AGENT_GRAPH_RELEASE_ID`;
Foundational publica los parsers puros y la capa de datos (migracion `0012`);
US1 dataset golden; US2 evals (runner + metrics + gate + persistencia); US3
releases versionadas y revertibles (activacion hibrida Q6 + stamp de
`release_id`); US4 presupuestos y rate limits (bloqueo duro recuperable Q3);
US5 dashboard del agente (P1); US6 ADR de proveedor de modelo (Q1); Polish el
harness, el flujo real opt-in, la arquitectura de capas y el cierre.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: puede ejecutarse en paralelo porque toca archivos distintos y no
  depende de una tarea incompleta.
- **[Story]**: historia de usuario de `spec.md`.
- Cada tarea nombra los paths exactos que crea o modifica.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Publicar los contratos machine-checkable de agent-evals, los
eventos de presupuesto y los settings que usaran todas las historias.

- [X] T001 [P] Publicar el dataset golden de conversaciones: 21 casos curados
  (7 familias x >=3: onboarding, ambiguous_change, explanation, comparison,
  feedback, injection, safe_refusal), cada uno con `context` redactado, `turns`
  y `expectation` (tool_calls con args y requires_confirmation, grounding,
  outcome), `reviewed_by`/`reviewed_at` y 0 PII en
  `contracts/agent-evals/v1/conversations-golden-v1.json`
- [X] T002 [P] Publicar el JSON Schema del golden con `registry_version` como
  `const: "conversations-golden-v1"` en
  `contracts/agent-evals/v1/conversations-golden.schema.json`
- [X] T003 [P] Publicar el registry append-only de releases del graph:
  `components` (prompt_versions, model_version, state_schema_version,
  topology_version, intent_schema_version, price_table_version,
  touches_prompts_or_model), `owner`/`justification`, `affected_case_ids`,
  `activation` (status/approved_by/approval_evidence/reverted_reason) y `date`
  en `contracts/agent-evals/v1/graph-releases-v1.json`
- [X] T004 [P] Publicar la tabla de precios por `model_version`
  (price_input_per_1k, price_output_per_1k, currency usd) en
  `contracts/agent-evals/v1/price-table-v1.json`
- [X] T005 [P] Agregar los 3 eventos de presupuesto al registry:
  `agent.budget_warning.v1`, `agent.budget_exhausted.v1`,
  `agent.rate_limit_exceeded.v1` (server, solo session_id y limit_kind, sin
  PII) en `contracts/events/v1/events-registry.json`
- [X] T006 [P] Agregar los settings `AGENT_EVALS_DATASET_VERSION`,
  `AGENT_EVALS_RELEASES_VERSION`, `AGENT_EVALS_PRICE_TABLE_VERSION`,
  `AGENT_EVALS_GATE_ENABLED` (true), `AGENT_EVALS_COST_THRESHOLD_PCT` (20),
  `AGENT_EVALS_LATENCY_THRESHOLD_MS` (1500), `AGENT_GRAPH_RELEASE_ID`
  (graph-release-001), `AGENT_BUDGET_WINDOW_HOURS` (24),
  `AGENT_BUDGET_SESSION_TOKEN_CAP` (150000), `AGENT_BUDGET_USER_TOKEN_CAP`
  (500000), `AGENT_BUDGET_SESSION_TOOL_CALL_CAP` (40),
  `AGENT_BUDGET_USER_COST_CAP_USD` (5.0),
  `AGENT_BUDGET_USER_CONCURRENCY_CAP` (2), `AGENT_BUDGET_WARNING_RATIO` (0.8)
  validados al iniciar y registrados en `_known_fields` en
  `src/umbral/infrastructure/config/settings.py` con test unit en
  `tests/unit/config/test_agent_settings.py`

**Checkpoint**: contratos y settings publicados; las historias tienen
dataset, releases, precios, eventos y limites disponibles.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Parsers puros de los contratos (bloqueantes de US1/US2/US3) y la
capa de datos (migracion `0012`) que US2/US3/US5 necesitan. Nada de las
historias de eval comienza sin esto.

**CRITICAL**: ninguna historia comienza hasta completar esta fase.

### Tests for Foundational

- [X] T007 [P] Escribir los unit tests de los parsers: golden (cobertura de
  las 7 familias x >=3, ids duplicados rechazados, tools/outcomes
  desconocidos rechazados, 0 PII), releases (casos referenciados existentes,
  inmutablez por entrada) y price (model_version conocidos) en
  `tests/unit/application/agent_evals/test_golden.py`,
  `tests/unit/application/agent_evals/test_releases.py`,
  `tests/unit/application/agent_evals/test_price.py`
- [X] T008 [P] Escribir el test de migracion: `0012_agent_evals` aplica y hace
  rollback, crea `agent_eval_suites` y `agent_eval_case_results` y agrega
  `agent_graph_runs.release_id` (string nullable) en
  `tests/migrations/test_0012_agent_evals.py`

### Implementation for Foundational

- [X] T009 [P] Definir las dataclasses `GoldenDataset`/`GoldenConversationCase`
  (familia, turns, expectation con tool_calls/grounding/outcome),
  `GraphRelease`/`GraphReleases` (components, affected_case_ids, activation),
  `PriceTableEntry` y el error tipado `AgentEvalsBlocked` (codigo
  `agent_evals.regression_blocked`) en `src/umbral/application/agent_evals/contracts.py`
- [X] T010 [P] Implementar `parse_golden_dataset` (cobertura de familias x
  >=3, validacion de ids/tools/outcomes, 0 PII) en
  `src/umbral/application/agent_evals/golden.py`
- [X] T011 [P] Implementar `parse_releases` y la regla de activacion (auto para
  componentes deterministas; `approved_by` + `approval_evidence` requeridos si
  `touches_prompts_or_model`, Q6) en
  `src/umbral/application/agent_evals/releases.py`
- [X] T012 [P] Implementar `parse_price_table` y `case_cost(model_calls, table)`
  (costo derivado de tokens x precio, recomputable) en
  `src/umbral/application/agent_evals/price.py`
- [X] T013 Escribir la migracion `0012_agent_evals` (`agent_eval_suites`,
  `agent_eval_case_results`, `agent_graph_runs.release_id`; downgrade
  completo) en `alembic/versions/0012_agent_evals.py` y actualizar el
  inventario cerrado de tablas en `scripts/check-migrations.ps1`

**Checkpoint**: parsers puros testeados y capa de datos desplegable; las
historias construyen sobre esto.

---

## Phase 3: US1 - Dataset golden de conversaciones

**Goal**: UM-H4-026 (FR-001..FR-004; SC-001): el dataset golden cubre las 7
familias con >=3 casos por familia (Q5), versionado e inmutable, revision de
producto registrada y 0 PII; cada caso define tools/argumentos/confirmaciones/
grounding/outcome esperados.

**Independent Test**: `tests/contract/test_agent_evals_golden.py` valida el
JSON publicado end-to-end (schema, cobertura de familias, expectations
completas, 0 PII, revision de producto) y falla ante cualquier caso invalido.

### Tests for US1

- [X] T014 [P] [US1] Escribir el conformance test del golden publicado: schema
  const, cobertura 7 familias x >=3 casos, cada `expectation` con
  tool_calls/grounding/outcome, `reviewed_by`/`reviewed_at` presentes y 0 PII
  en `tests/contract/test_agent_evals_golden.py`

### Implementation for US1

- [X] T015 [US1] Verificar la curaduria del dataset publicado: los 21 casos de
  `contracts/agent-evals/v1/conversations-golden-v1.json` cubren las 7
  familias (>=3 cada una), las expectativas de los casos de cambios ambiguos
  exigen aclaracion previa y los de injection/rechazo seguro declaran el
  limite con 0 tools no permitidas (check de contenido sobre el JSON; sin
  codigo)

**Checkpoint**: FR-001..FR-004; SC-001.

---

## Phase 4: US2 - Evals automatizados del graph

**Goal**: UM-H4-027 (FR-005..FR-008; SC-002): suite de evals sobre el stack v3
REAL con adapter determinista (Q4), metricas por caso derivadas de runs
persistidos (seleccion de tool, argumentos, grounding, confirmacion, outcome,
costo), reproducibilidad y gate de regresiones estricto en señales
deterministas con umbrales de politica para costo/latencia (Q2).

**Independent Test**: `tests/integration/agent_evals/test_suite_lifecycle.py`
corre el suite completo sobre Postgres con el gateway scriptado y verifica que
el 100% de los casos produce metricas, que dos corridas producen el mismo
reporte y que el gate persiste `passed`/`blocked`.

### Tests for US2

- [X] T016 [P] [US2] Escribir los unit tests de metrics: seleccion de tool y
  argumentos contra el contrato de tools, grounding (refs que resuelven a
  evidencia persistida en scope), cumplimiento de confirmacion (0 efectos sin
  confirmacion), clase de outcome y costo (tokens x tabla de precios) en
  `tests/unit/application/agent_evals/test_metrics.py`
- [X] T017 [P] [US2] Escribir los unit tests del runner: por caso envia los
  turns sobre el stack real, registra runs y extrae las metricas; 2 corridas
  del mismo suite sobre la misma release producen el mismo reporte en
  `tests/unit/application/agent_evals/test_runner.py`
- [X] T018 [P] [US2] Escribir los tests del gate de regresiones: baseline ==
  candidato pasa; desvio en una señal determinista sin release declarada
  bloquea (`agent_evals.regression_blocked`); `affected_case_ids` que no
  coinciden con el diff detectado bloquea (`agent_evals.release_mismatch`);
  costo/latencia usan umbrales de politica en
  `tests/unit/application/agent_evals/test_evals_regression.py` y el conformance
  `tests/contract/test_agent_evals_regression.py`
- [X] T019 [P] [US2] Escribir el conformance test de la tabla de precios:
  cubre los `model_version` de las releases publicadas y parsea contra el
  schema en `tests/contract/test_agent_evals_price.py`

### Implementation for US2

- [X] T020 [P] [US2] Implementar el `ScriptedModelGateway` determinista:
  respuestas scriptadas por `prompt_version` y registro de calls (tokens,
  latency, model_version), reutilizando el patron del `FakeModelGateway`
  existente en `src/umbral/infrastructure/agent_evals/scripted_gateway.py`
- [X] T021 [US2] Implementar `build_eval_stack_v3`: composicion del stack v3
  real (`build_topology_v3` + `ChatRuntime`) con gateway y recorder inyectados
  (sin dependencia del wiring de la API) en
  `src/umbral/infrastructure/agent_evals/composition.py`
- [X] T022 [US2] Implementar las metricas deterministas por caso
  (`tool_selection_ok`, `args_valid`, `grounding_ok`, `confirmation_ok`,
  `outcome_ok`, `case_cost`, `case_latency`) derivadas de los runs registrados
  y del contrato de tools en `src/umbral/application/agent_evals/metrics.py`
- [X] T023 [US2] Implementar `run_suite`: por caso crea sesion, envia los turns
  con el gateway scriptado, registra los runs reales y extrae las metricas en
  `src/umbral/application/agent_evals/runner.py`
- [X] T024 [US2] Implementar `run_regression`: veredictos por caso
  (tool_selection_change, args_change, grounding_change, confirmation_change,
  outcome_change bloquean con 0 tolerancia; cost_delta/latency_delta con
  umbrales de politica), match exacto con `affected_case_ids` declarados y
  reporte agregado sin PII en `src/umbral/application/agent_evals/regression.py`
- [X] T025 [US2] Implementar `SqlAlchemyEvalSuiteRepository` y
  `SqlAlchemyEvalCaseResultRepository` sobre los modelos de la migracion
  `0012` en `src/umbral/infrastructure/agent_evals/repositories.py`
- [X] T026 [US2] Escribir el test de integracion del ciclo de suite (Postgres
  via testcontainers): `running` -> `passed`/`blocked` persistido con
  `gateway_fidelity`, metricas agregadas y resultados por caso; 2 corridas
  reproducibles; release activa vs candidata en
  `tests/integration/agent_evals/test_suite_lifecycle.py`

**Checkpoint**: FR-005..FR-008; SC-002.

---

## Phase 5: US3 - Releases versionadas y revertibles

**Goal**: UM-H4-028 (FR-009..FR-011; SC-003): cada cambio de prompts/modelos/
schemas/topologia es una release inmutable que registra sus componentes; cada
run referencia su release (`agent_graph_runs.release_id`); comparar y revertir
0 muta runs previos; activacion hibrida (Q6).

**Independent Test**: `tests/integration/agent_evals/test_run_release_stamp.py`
verifica que los runs sellan su `release_id`, que al revertir los runs nuevos
usan la release anterior y que los runs ya ejecutados no se tocan.

### Tests for US3

- [X] T027 [P] [US3] Escribir los unit tests de la regla de activacion: auto
  con gate verde para cambios deterministas; `approved_by` +
  `approval_evidence` obligatorios si `touches_prompts_or_model` (Q6); revert
  como entrada nueva con motivo; 0 mutacion de entradas previas en
  `tests/unit/application/agent_evals/test_releases_activation.py`
- [X] T028 [P] [US3] Escribir el conformance test del registry de releases:
  parsea contra el dataset publicado, `affected_case_ids` existen y la entrada
  inicial es `active` en `tests/contract/test_agent_evals_releases.py`
- [X] T029 [P] [US3] Escribir el test de integracion del stamp: un run sella su
  `release_id` desde `AGENT_GRAPH_RELEASE_ID`; tras un revert los runs nuevos
  usan la release anterior y los previos conservan la suya (0 reescrituras) en
  `tests/integration/agent_evals/test_run_release_stamp.py`

### Implementation for US3

- [X] T030 [US3] Implementar la regla de activacion en
  `src/umbral/application/agent_evals/releases.py` (auto vs aprobacion de
  operador con evidencia; reversion con motivo y responsable) y su exposicion
  al gate
- [X] T031 [US3] Implementar el stamp de `release_id` en `ChatRuntime.run_turn`
  (desde `AGENT_GRAPH_RELEASE_ID`, registrado en `AgentGraphRun`) y el modelo
  `agent_graph_runs.release_id` en `src/umbral/agent/runtime.py` y
  `src/umbral/infrastructure/db/models/agent.py`

**Checkpoint**: FR-009..FR-011; SC-003.

---

## Phase 6: US4 - Presupuestos y rate limits

**Goal**: UM-H4-029 (FR-012..FR-016; SC-004): limites de tokens, tools,
concurrencia y costo por usuario/sesion en ventana de politica; advertencia
previa; bloqueo duro recuperable al agotar (Q3); rechazo tipado de
concurrencia; eventos auditables sin PII.

**Independent Test**: `tests/integration/agent_evals/test_agent_budgets.py` ejerce
cada limite (tokens, tools, concurrencia, costo) con sesiones reales y
manipuladas y verifica que el 100% de los excesos se detiene, comunica y
recupera, con 0 ejecuciones que exceden el presupuesto.

### Tests for US4

- [X] T032 [P] [US4] Escribir los unit tests de budgets: `BudgetPolicy`
  (ventana, caps, ratio), `evaluate_budget` (ok/warning/exhausted por ratio y
  caps), `compute_consumption` desde runs x tabla de precios, y 0 acceso a
  presupuestos ajenos en `tests/unit/application/agent/test_budgets.py`
- [X] T033 [P] [US4] Escribir el test de integracion de budgets: advertencia
  sin interrumpir el turno en curso, bloqueo duro recuperable (estado tipado,
  ventana o accion explicita, 0 degradacion de modelo), corte tipado a mitad
  de un turno por tokens, concurrencia por usuario rechazada y eventos
  auditables sin PII en `tests/integration/agent_evals/test_agent_budgets.py`

### Implementation for US4

- [X] T034 [US4] Implementar la logica pura de presupuestos (`BudgetPolicy`,
  `evaluate_budget`, `compute_consumption`) en
  `src/umbral/application/agent/budgets.py`
- [X] T035 [US4] Implementar el lector de consumo desde los registros
  (`agent_model_calls` x tabla de precios, tool calls de `agent_node_runs`,
  runs activos para concurrencia) en `src/umbral/infrastructure/agent/budgets.py`
- [X] T036 [US4] Implementar el gate pre-run de presupuesto en
  `ChatRuntime.run_turn` (estado tipado `agent.budget_exhausted`, advertencia
  `agent.budget_warning`, corte tipado si el turno excede tokens) en
  `src/umbral/agent/runtime.py`
- [X] T037 [US4] Mapear los errores tipados de presupuesto en
  `api/routers/chat.py` (`agent.budget_warning`/`agent.budget_exhausted`/
  `agent.rate_limit_exceeded` con `_problem_for`) y aplicar el limite de
  concurrencia por usuario (0 colas, estado tipado)

**Checkpoint**: FR-012..FR-016; SC-004.

---

## Phase 7: US5 - Dashboard del agente (P1)

**Goal**: UM-H4-030 (FR-017..FR-019; SC-005): vista operativa interna de solo
lectura que agrega latencia, errores, tool success, interrupts, tokens, costo
y regresiones de eval vinculadas a su release; `data_as_of`; 0 PII; 0
mutaciones.

**Independent Test**: `tests/integration/agent_ops/test_overview.py` genera
runs y evals conocidos y verifica que el overview muestra las mismas cifras
que los registros fuente y las regresiones vinculadas a su release y gate.

### Tests for US5

- [X] T038 [P] [US5] Escribir los unit tests del servicio de overview:
  agregados (latency_p95, error_rate, tool_success_rate, interrupts, tokens,
  costo) calculados sin PII y con `data_as_of` en
  `tests/unit/application/agent_ops/test_ops_service.py` (basename unico)
- [X] T039 [P] [US5] Escribir el test de integracion del overview: las cifras
  coinciden con `agent_graph_runs`/`agent_node_runs`/`agent_model_calls`/
  `agent_eval_suites`, las regresiones aparecen vinculadas a su release y
  gate, y 0 PII en `tests/integration/agent_ops/test_overview.py`
- [X] T040 [P] [US5] Escribir el vitest de la pagina ops: renderiza agregados y
  `data_as_of`, sin acciones de mutacion en
  `apps/web/src/app/(protected)/ops/agent/ops-page.test.tsx`

### Implementation for US5

- [X] T041 [US5] Implementar `application/agent_ops`: `OpsDashboardReport`
  (data_as_of), puertos y `OpsOverviewService` (agregados puros, 0 PII) en
  `src/umbral/application/agent_ops/`
- [X] T042 [US5] Implementar el repo de agregacion sobre los registros de
  runs/evals en `src/umbral/infrastructure/agent_ops/overview.py`
- [X] T043 [US5] Implementar `api/routers/agent_ops.py`: `GET /api/v1/agent/ops/
  overview` de solo lectura protegido por `product.agent_ops.read`, con
  `data_as_of` y traduccion tipada; registrar el router en `src/umbral/api/main.py`
- [X] T044 [US5] Agregar la access action `product.agent_ops.read` en
  `src/umbral/domain/identity/policy.py`
- [X] T045 [US5] Implementar la pagina read-only `(protected)/ops/agent` y el
  BFF `app/api/agent/ops/overview/route.ts` en `apps/web/src/` (0 PII, 0
  mutaciones, antiguedad visible)

**Checkpoint**: FR-017..FR-019; SC-005.

---

## Phase 8: US6 - ADR de proveedor de modelo

**Goal**: FR-022 (SC-006; Q1): documento versionado que compara alternativas
de proveedor con criterios explicitos (costo, calidad, latencia, privacidad,
operabilidad) con evidencia de los evals del dataset golden, registra
decision, riesgos y monitoreo, y queda referenciado por el repo y el harness.

**Independent Test**: `tests/contract/test_model_provider_adr.py` valida la
estructura y versionado del ADR publicado.

### Tests for US6

- [X] T046 [P] [US6] Escribir el test de estructura del ADR: existe, versionado
  (fecha y responsable), compara alternativas con los 5 criterios, registra
  decision, riesgos y monitoreo en `tests/contract/test_model_provider_adr.py`

### Implementation for US6

- [X] T047 [US6] Redactar `docs/decision-records/0001-model-provider.md`:
  alternativas comparadas con evidencia de los evals del dataset golden
  (costo, calidad, latencia, privacidad, operabilidad), decision, riesgos y
  monitoreo acordado (alimenta price table y presupuestos; el proveedor local
  sigue `"fake"`)

**Checkpoint**: FR-022; SC-006.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Arquitectura de capas, harness `check-evals.ps1` registrado en
`check.ps1` (gate en adapter simulado, Q4), flujo real opt-in
`run-real-evals.ps1`, OpenAPI/cliente web y cierre con evidencia.

- [X] T048 [P] Escribir el test de arquitectura de capas: `application/agent_evals`
  y `application/agent_ops` no importan infrastructure/agent/api/workers ni
  fastapi/sqlalchemy/langgraph; api/workers no importan los modulos de eval en
  `tests/architecture/test_agent_evals_boundaries.py`
- [X] T049 [P] Crear `scripts/check-evals.ps1` (paths obligatorios: contract
  agent_evals + ADR, unit agent_evals + budgets + agent_ops, integration
  agent_evals + agent_ops, migrations 0012, architecture, config) y
  registrarlo en `check.ps1` con deteccion de superficie
  (`src\umbral\application\agent_evals` +
  `tests\contract\test_agent_evals_golden.py`)
- [X] T050 [P] Crear `scripts/run-real-evals.ps1`: flujo opt-in con proveedor
  real (presupuesto de eval acotado por politica, fuera de CI) y referenciarlo
  en el CLI de workers (`tests/unit/workers/test_cli.py`)
- [X] T051 [P] Re-exportar el OpenAPI (`scripts/export-openapi.ps1`),
  regenerar el cliente web (`npm --workspace @umbral/web run api:generate`) y
  verificar 0 drift con `api:check` (path de agent ops) en
  `contracts/openapi/v1/openapi.json`
- [X] T052 Cerrar: correr los 7 escenarios de `quickstart.md` y
  `.\scripts\check.ps1` desde checkout limpio (incluye `check-evals.ps1` y
  `check-web.ps1`); registrar evidencia en
  `docs/runbooks/evidence/graph-evals-ops-acceptance.md` y marcar UM-H4-026 a
  UM-H4-030 en `docs/product/backlog.md`

**Checkpoint**: FR-020, FR-021; SC-007. Incremento cerrado con evidencia.

---

## Dependencies

- T001..T006 (Setup) -> T007..T013 (Foundational) -> US1 -> US2 -> US3 -> US4
  -> US5 -> US6 -> Polish.
- Fases con **historia** dependen de Foundational (T007..T013): los parsers
  puros y la migracion `0012` son prerrequisitos bloqueantes.
- US2 depende de US1 (el dataset golden alimenta el runner) y de Foundational
  (parsers + migracion). US3 depende de US2 en el sentido de que la release
  candidata se valida contra el gate (T024/T026) y de la migracion (T013).
- US4 depende de los settings de presupuesto (T006), del registro de consumo
  de runs (H4.1, existente) y de la tabla de precios (T012); el runtime gate
  (T036) depende del stack v3 existente (H4.3).
- US5 depende de la migracion `0012` (T013), de los repos de eval (T025) y del
  cliente web regenerado (T051, puede adelantarse en Polish).
- US6 es independiente de las otras historias salvo de la evidencia del
  dataset golden (T015) para sus evaluaciones de calidad.
- Polish depende de todas las historias; T048 (arquitectura) depende de los
  modulos `application/agent_evals` y `application/agent_ops`; T052 (cierre)
  depende de todo.

## Parallel Opportunities

- Setup: T001..T006 (6 tareas paralelas, archivos distintos).
- Foundational: T007/T008 (tests) y T009..T013 (implementacion; T013
  migracion al final de la fase).
- US2: T016..T019 (tests paralelos) y T020..T025 (implementacion; T020 gateway
  antes de T023 runner).
- US3: T027..T029 (tests paralelos) y T030/T031.
- US4: T032/T033 (tests) y T034..T037.
- US5: T038/T039/T040 (tests paralelos) y T041..T045.
- US6: T046 (test) y T047 (documento) en paralelo con US2/US4/US5.
- Tras US2: US3 y US4 en paralelo (archivos distintos: releases vs budgets).
- Polish: T048..T051 paralelas salvo T052 (cierre).

## Implementation Strategy (MVP -> full)

- MVP: US1 + US2 completos (dataset golden + evals con gate) sobre los
  parsers y la migracion `0012`: el gate corre en adapter simulado y detecta
  regresiones de la release vigente — es el slice de valor central de la
  epica.
- Siguiente: US3 (releases con activacion hibrida y stamp de `release_id`) —
  cierra la trazabilidad de cambios del graph.
- Luego: US4 (presupuestos y rate limits) y US5 (dashboard, P1) en paralelo;
  US6 (ADR) en paralelo con ambas (documento independiente).
- Cierre: Polish (arquitectura + harness + flujo real opt-in + OpenAPI +
  evidencia).
