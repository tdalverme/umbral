# Research: Evals, costos y operacion del agente (H4.4)

Resolucion de las incognitas del Technical Context y decisiones de diseno para
el plan de UM-H4-026 a UM-H4-030 + ADR de proveedor de modelo.

## R-01 - Dataset golden de conversaciones: contrato JSON versionado

**Decision**: dataset publicado como `contracts/agent-evals/v1/conversations-golden-v1.json` (+ `conversations-golden.schema.json`), con parser puro en `application/agent_evals/golden.py`, replicando la convencion de `contracts/matching/v1/golden-dataset-v1.json` (H3.4): `registry_version` constante, `reviewed_by`/`reviewed_at` por producto, casos autocontenidos e inmutables por version.

**Rationale**: la spec (FR-001..FR-004) exige dataset versionado e inmutable, 0 PII, revision de producto y minimo 3 casos por familia (21 total, clarificacion Q5). El patron H3.4 ya resuelve exactamente esto (archivo publicado, schema const, tags de cobertura, conformance test); replicarlo evita inventar una mecanica nueva.

**Alternativas consideradas**: (a) dataset en la base de datos — rechazada: el dataset debe ser versionable y diffable como artefacto de contrato, y la convencion del repo es JSON publicado; (b) fixtures solo en tests — rechazada: FR-003 exige revision de producto registrada y consultable, no un fixture de tests.

## R-02 - Caso golden de conversacion: forma de la expectativa

**Decision**: cada caso define: `family` (7 familias), `context` (perfil/radar/listing redactado o sintetico), `turns` (mensajes del usuario) y `expectation`: secuencia esperada de `tool_calls` (tool + argumentos + `requires_confirmation`), restricciones de `grounding` (refs exigidas), `outcome` (completed | clarification | safe_refusal | failed) y `tags`.

**Rationale**: FR-002 exige tools/argumentos/confirmaciones/grounding/outcome esperados; la clase de outcome ya aparece en el spec. La expectativa debe ser maquina-comparable contra los registros del run (ModelCall/ToolRun/NodeRun + estado).

**Alternativas consideradas**: (a) transcripciones libres evaluadas con LLM-as-judge — rechazada: el gate es estricto y determinista (Q2); (b) solo verificacion de outcome sin detalle de tools — rechazada: FR-005 exige medir seleccion de tool y argumentos por caso.

## R-03 - Eval runner: el graph real con gateway determinista

**Decision**: el runner evalua el graph REAL (`build_topology_v3` + `ChatRuntime`), no una simulacion de nodos: por cada caso crea sesion, envia los turns con el gateway scriptado (respuestas deterministas por `prompt_version`, extension del `FakeModelGateway` existente que ya keyea por prompt_version), registra runs reales (GraphRun/NodeRun/ModelCall) y extrae las metricas de los registros + estado.

**Rationale**: la convencion de los incrementos H4.1-H4.3 es ejercitar el stack real con fake gateway (0 mock de superficie); evaluar el graph real valida contratos, politica de intent, HITL y grounding de verdad. FR-007 exige reproducibilidad: con adapter determinista, dos corridas producen el mismo reporte (clarificacion Q4: el gate corre simulado; el proveedor real corre en flujo separado).

**Alternativas consideradas**: (a) evaluar solo nodos sueltos — rechazada: no cubre integracion de contratos ni HITL; (b) evaluar con el proveedor real en el gate — rechazada (Q4): costo, latencia y flakiness; la varianza se registra solo en el flujo real.

## R-04 - Metricas de eval: derivadas de registros, no de texto

**Decision**: metricas por caso derivadas deterministicamente de los registros: seleccion de tool (ToolRun vs expectativa), validez de argumentos (validacion contra el contrato de tools `parse_tool_contract`), grounding (cada ref del reply resuelve a evidencia persistida dentro del scope de la sesion), cumplimiento de confirmacion (0 efectos sin confirmacion: secuencia propose→approve esperada), clase de outcome, y costo = Σ(ModelCall tokens × precio de la tabla de la release).

**Rationale**: FR-005/FR-006 definen exactamente estas metricas y la constitucion exige 0 ranking/efectos generativos — las metricas deben computarse de evidencia estructurada (runs), nunca del texto.

**Alternativas consideradas**: (a) LLM-as-judge para grounding/outcome — rechazada: gate estricto determinista (Q2) y 0 decisiones de calidad generativas (principio II); (b) metricas desde el estado del checkpoint — rechazada: el estado es operacional y la fuente de verdad auditable son los runs persistidos (principio I/V).

## R-05 - Costo: tabla de precios versionada por release

**Decision**: `contracts/agent-evals/v1/price-table-v1.json` con precio por `model_version` (input/output por 1k tokens); el costo por caso y por suite se calcula de los ModelCalls registrados (H4.1 ya persiste tokens por call) contra la tabla de la release. 0 costo almacenado: se deriva (auditable y recomputable).

**Rationale**: FR-005/FR-006 piden costo por caso; la fuente de tokens ya existe (`agent_model_calls`); derivar evita tablas de consumo adicionales y permite recalcular con precios actualizados sin mutar runs (principio V).

**Alternativas consideradas**: (a) columna `cost_usd` en ModelCall — rechazada: duplica estado derivado y desactualiza si la tabla cambia; (b) costeo solo agregado sin desglose — rechazada: FR-005 exige costo por caso.

## R-06 - Releases del graph: registry append-only en contratos + `release_id` en runs

**Decision**: `contracts/agent-evals/v1/graph-releases-v1.json` (registry `graph-releases-v1`, append-only, immutabilidad por entrada) donde cada release registra sus componentes (prompt versions, model version, state_schema_version, topology_version, intent schema, price table), `owner`, `justification`, `affected_case_ids` y el estado de activacion: `approved_by`/`approval_evidence` cuando el cambio toca prompts/modelos (activacion hibrida, Q6). El run referencia su release via `agent_graph_runs.release_id` (string, nullable; columna en migracion 0012); el runtime la sella desde settings (`AGENT_GRAPH_RELEASE_ID`).

**Rationale**: FR-009..FR-011 exigen release versionada e inmutable, 0 reescrituras de runs y reversion con motivo. El registro JSON append-only replica la convencion de releases de H3.4 (`releases-v1.json`) y la inmutablez es estructural; "revert" = entrada nueva con `reverted: true` + motivo + responsable; los runs nunca se mutan. La activacion hibrida (Q6) queda en los campos de aprobacion de la entrada.

**Alternativas consideradas**: (a) tabla `graph_releases` en Postgres — rechazada: el registro debe ser diffable/versionado como contrato y la convencion H3.4 es file-based; (b) release implicita por conjunto de versiones — rechazada: FR-009 exige un artefacto explícito, inmutable y con responsable.

## R-07 - Gate de regresiones: estricto en señales deterministas + umbrales

**Decision**: `application/agent_evals/regression.py` replica el patron de `matching/regression.py`: corre el suite con baseline y candidate sobre el mismo dataset (adapter determinista), produce veredictos por caso — `tool_selection_change`, `args_change`, `grounding_change`, `confirmation_change`, `outcome_change` (bloquean, 0 tolerancia) y `cost_delta`/`latency_delta` (umbrales de politica `AGENT_EVALS_COST_THRESHOLD_PCT`/`LATENCY_THRESHOLD_MS`) — y valida que los casos afectados declarados en la release coincidan exactamente con los detectados (`agent_evals.release_mismatch`/`undeclared_change`, error tipado `AgentEvalsBlocked`).

**Rationale**: Q2 fija gate estricto en señales deterministas con umbrales para costo/latencia, y la convencion H3.4 ya implementa el patron de gate estricto con releases declaradas; la evaluacion de grounding/confirmacion/outcome es determinista porque corre sobre registros (R-04).

**Alternativas consideradas**: (a) gate blando con tolerancias por métrica — rechazada (Q2): 0 tolerancia en lo determinista; (b) gate solo de reporte — rechazada (Q2): el backlog exige bloquear cambios no explicados.

## R-08 - Persistencia de evals: migracion 0012

**Decision**: migracion `0012_agent_evals` agrega `agent_eval_suites` (dataset_version, baseline_release_id, candidate_release_id, gateway_fidelity enum simulated|real, status, blocked, metrics JSONB, timestamps) y `agent_eval_case_results` (suite_id, case_id, metricas por caso, verdict, reason), mas `agent_graph_runs.release_id` (string nullable). Inventario cerrado de `check-migrations.ps1` se actualiza.

**Rationale**: FR-006 exige resultados registrados con release y dataset; el dashboard (FR-017) agrega runs y evals. Dos tablas + una columna es el minimo que satisface las FR sin duplicar registros existentes (0 tabla de consumo: R-05).

**Alternativas consideradas**: (a) resultados de eval solo en archivos JSON — rechazada: el dashboard y la trazabilidad requieren consulta y correlacion con runs; (b) suite por caso individual sin agregado — rechazada: FR-006 exige reporte por caso y agregado vinculado a la suite.

## R-09 - Presupuestos y rate limits: logica pura + enforcement en runtime

**Decision**: `application/agent/budgets.py` con logica pura: `BudgetPolicy` (tokens por sesion/usuario, tool calls por sesion, costo USD por usuario, concurrencia por usuario, ventana, ratio de advertencia) y `evaluate_budget(policy, consumption, now) -> ok|warning|exhausted`. El consumo se computa de los registros (tokens/costo de ModelCall × tabla de precios, tool calls de ToolRun, runs activos para concurrencia). Enforcement: pre-run en `ChatRuntime` (estado tipado `agent.budget_exhausted`, advertencia `agent.budget_warning`) y rechazo de concurrencia en el router (H4.1 ya impide 0 paralelas por sesion; aqui el limite es por usuario). Recuperacion: ventana (default 24h) o accion explicita; 0 degradacion de modelo (Q3). Nuevos eventos `agent.budget_warning.v1`, `agent.budget_exhausted.v1`, `agent.rate_limit_exceeded.v1` (FR-016).

**Rationale**: FR-012..FR-016 exigen limites aplicados, advertencia previa, bloqueo duro recuperable (Q3), rechazo tipado de concurrencia y eventos auditables sin PII; el runtime y el router son los puntos de enforcement existentes y la logica pura se testea sin infra.

**Alternativas consideradas**: (a) tabla de consumo — rechazada: computar de los runs es determinista, auditable y 0 estado derivado (R-05); (b) degradacion suave — rechazada (Q3): bloqueo duro recuperable, 0 cambio de modelo; (c) enforcement solo en API — rechazada: un run en curso podria exceder tokens sin control; el runtime lo corta con estado tipado.

## R-10 - Dashboard del agente: endpoint interno de solo lectura + pagina minima

**Decision**: `application/agent_ops/` (service puro sobre puertos) + repo infra que agrega `agent_graph_runs`/`agent_node_runs`/`agent_model_calls`/`agent_eval_suites` (latencia, errores, tool success, interrupts, tokens, costo, regresiones de eval), endpoint `api/routers/agent_ops.py` de solo lectura protegido por access action `product.agent_ops.read`, y pagina web minima read-only `(protected)/ops/agent`. 0 PII (solo agregados), marca de antiguedad de datos (FR-018), 0 mutaciones (FR-019).

**Rationale**: P1 (UM-H4-030); la spec lo define interno, solo lectura, sin PII. La web no tiene layout admin; una pagina minima con los agregados es suficiente y sigue la convencion BFF existente.

**Alternativas consideradas**: (a) dashboard como vista del usuario — rechazada: spec lo define interno (0 superficie de producto); (b) grafana/prometheus — rechazada: sin nueva infraestructura para V1 (constitucion); (c) dashboard solo API sin pagina — rechazada: la pagina minima da valor operativo real y es barata.

## R-11 - ADR de proveedor de modelo

**Decision**: `docs/decision-records/0001-model-provider.md` (nueva convencion documentada en el plan), comparando alternativas con criterios explicitos (costo, calidad, latencia, privacidad, operabilidad), con evidencia de los evals del dataset golden (Q1: se incluye como entregable; FR-022), decision, riesgos y monitoreo; `tests/contract/test_model_provider_adr.py` valida estructura/versionado y queda en el harness. La eleccion alimenta la tabla de precios (R-05) y los presupuestos (R-09); `AGENT_MODEL_PROVIDER` sigue en `"fake"` para local.

**Rationale**: Q1 resuelto: el ADR cierra el diferido asignado a H4.4 en tres notas de aceptacion y queda vinculado al harness (FR-022). Documento versionado, no codigo: la decision es de producto/arquitectura con evidencia de evals.

**Alternativas consideradas**: (a) ADR sin vinculo al harness — rechazada (Q1: queda referenciado por el repo y el harness); (b) aplazar a H6 — rechazada: tres notas de aceptacion lo asignan explicitamente a H4.4 y condiciona presupuestos y dashboard.

## R-12 - Flujo de evals con proveedor real y harness

**Decision**: `scripts/check-evals.ps1` (registrado en `check.ps1` con surface detection, convencion de incrementos previos) corre dataset, runner con adapter determinista, gate, releases, presupuestos, dashboard y ADR; `scripts/run-real-evals.ps1` es el flujo separado, opt-in y con presupuesto de eval acotado por politica (Q4: el proveedor real nunca esta en el gate ni en CI).

**Rationale**: FR-020 (harness dedicado) y Q4 (evals hibridos); la convencion de harness por dominio esta establecida en los 11 incrementos previos.

**Alternativas consideradas**: (a) evals reales dentro de check.ps1 — rechazada (Q4): costo y flakiness en CI; (b) 0 flujo real — rechazada: FR-005/ADR necesitan evidencia con el modelo de produccion.

## Dependencias y convenciones confirmadas (no reimplementar)

- Runs versionados y auditables: `AgentGraphRun` (state/topology versions, token_usage JSONB, latency, error_summary), `AgentNodeRun`, `AgentModelCall` (model/prompt/schema versions, tokens, latency, status) — H4.1 (R-03/R-06).
- Gateway intercambiable: `ModelGateway` port + `FakeModelGateway` determinista (keyea por `prompt_version`) + `ManagedModelGateway` HTTP — H4.1; el eval extiende el fake con respuestas scriptadas por caso.
- Topologia v3 + intent + HITL + grounding: `build_topology_v3`, `IntentCompiler`, `ToolExecutor`, `require_confirmation`, `persist_reply` — H4.3; el runner evalua este stack real.
- Convencion golden/releases/gate: `application/matching/{golden,releases,regression}.py` + contratos `matching/v1/*` — H3.4 (R-01/R-06/R-07).
- Harness: `scripts/check-*.ps1` con surface detection en `check.ps1`; conformance en `tests/contract/`; integracion con testcontainers por dominio; migracion con inventario cerrado en `check-migrations.ps1` — convencion de los 11 incrementos previos (R-12).
- Events registry: `contracts/events/v1/events-registry.json` + `validate_event` — se agregan 3 tipos (R-09).
- Import-linter: `application/*` no importa infra/agent/api; `tests/architecture/*` pin por AST — R-03/R-07/R-10.
