# Data Model: Evals, costos y operacion del agente (H4.4)

Entidades del incremento. Los contratos JSON publicados son la fuente de
verdad de los datasets y registros; la migracion `0012_agent_evals` persiste
solo los resultados de eval y el vinculo release↔run.

## Entidades de contrato (publicadas, inmutables por version)

### GoldenConversationCase — `contracts/agent-evals/v1/conversations-golden-v1.json`

Dataset versionado (`registry_version: "conversations-golden-v1"`,
`contract_version: "1"`), revisado por producto (`reviewed_by`,
`reviewed_at`), minimo 3 casos por familia (21 total, Q5).

| Campo | Tipo | Reglas / validacion |
| --- | --- | --- |
| `id` | string | unico, formato `conversation-###` |
| `family` | enum | `onboarding` | `ambiguous_change` | `explanation` | `comparison` | `feedback` | `injection` | `safe_refusal` |
| `context` | object | `profile` (criterios redactados), `listings` (opcional, redactados); 0 PII |
| `turns` | array[string] | 1..N mensajes del usuario (espanol CABA) |
| `expectation.tool_calls` | array | secuencia esperada: `tool` (nombre del contrato de tools), `args` (objeto), `requires_confirmation` (bool), `order` (int) |
| `expectation.grounding` | object | `require_refs` (bool), `min_refs` (int >= 1), `declare_missing` (bool) |
| `expectation.outcome` | enum | `completed` | `clarification` | `safe_refusal` | `failed` |
| `tags` | array | cobertura requerida: `requires_confirmation`, `interrupts`, `injection`, `rejects` |
| `notes` | string | revision de producto por caso |

Cobertura obligatoria (parser `application/agent_evals/golden.py`): el
dataset debe incluir al menos 3 casos por familia y los tags de cobertura
acordados; ids duplicados y outcomes/tools desconocidos se rechazan.

### GraphRelease — `contracts/agent-evals/v1/graph-releases-v1.json`

Registry append-only (`registry_version: "graph-releases-v1"`); cada entrada
es inmutable (0 ediciones posteriores).

| Campo | Tipo | Reglas |
| --- | --- | --- |
| `id` | string | unico, `graph-release-###` |
| `components.prompt_versions` | array[string] | prompts incluidos (intent/reply) |
| `components.model_version` | string | modelo (de la tabla de precios) |
| `components.state_schema_version` | string | `chat-state-v3` |
| `components.topology_version` | string | `chat-topology-v3` |
| `components.intent_schema_version` | string | `intent-schema-v3` |
| `components.price_table_version` | string | tabla de precios usada para costo |
| `components.touches_prompts_or_model` | bool | activa la regla de aprobacion (Q6) |
| `owner` / `justification` | string | responsable y explicacion |
| `affected_case_ids` | array[string] | casos del dataset que cambian; el gate exige coincidencia exacta con el diff detectado (R-07) |
| `activation` | object | `status` (`pending` | `active` | `reverted`), `approved_by` (requerido si `touches_prompts_or_model`), `approval_evidence` (reporte de eval), `reverted_reason` (si revert) |
| `date` | string | ISO |

Reglas: el cambio de componentes deterministas (state schema, topology,
schemas) activa automaticamente con gate verde; el cambio de
prompts/modelos exige `approved_by` + `approval_evidence` (Q6). La release
activa = ultima entrada con `status: active`. Revert = entrada nueva con
`status: reverted` + motivo; los runs nunca se mutan (FR-010).

### PriceTable — `contracts/agent-evals/v1/price-table-v1.json`

`registry_version: "price-table-v1"`, lista de `{model_version, price_input_per_1k, price_output_per_1k, currency: "usd"}`. El costo de un case/suite se deriva de los `AgentModelCall.tokens` de la suite contra la tabla de la release evaluada (R-05).

## Entidades persistidas (migracion `0012_agent_evals`)

### agent_eval_suites

| Columna | Tipo | Reglas |
| --- | --- | --- |
| `eval_suite_id` | uuid PK | unico |
| `dataset_version` | string | version del golden evaluado |
| `baseline_release_id` | string | release vigente (FR-006) |
| `candidate_release_id` | string nullable | release candidata; null en evals de monitoreo |
| `gateway_fidelity` | enum | `simulated` | `real` (Q4) |
| `status` | enum | `running` | `passed` | `blocked` |
| `blocked_reasons` | JSONB nullable | razones del gate (0 PII) |
| `metrics` | JSONB | agregadas: tool_accuracy, args_valid, grounding_coverage, confirmation_compliant, outcome_match, cost_per_case_avg, latency_avg |
| `started_at` / `finished_at` | timestamptz | latencia de la suite |

### agent_eval_case_results

| Columna | Tipo | Reglas |
| --- | --- | --- |
| `eval_case_result_id` | uuid PK | unico |
| `eval_suite_id` | uuid FK → agent_eval_suites | pertenencia a la suite (CASCADE) |
| `case_id` | string | id del caso golden |
| `tool_selection_ok` / `args_valid` / `grounding_ok` / `confirmation_ok` / `outcome_ok` | bool | señales deterministas |
| `cost_usd` | numeric(10,4) | costo del caso derivado (R-05) |
| `latency_ms` | int | latencia del caso |
| `verdict` | enum | `ok` | `tool_selection_change` | `args_change` | `grounding_change` | `confirmation_change` | `outcome_change` | `cost_delta` | `latency_delta` |
| `reason` | string nullable | 0 PII |

### agent_graph_runs (+ `release_id`)

| Columna | Tipo | Reglas |
| --- | --- | --- |
| `release_id` | string nullable | release que produjo el run (FR-010); se sella desde `AGENT_GRAPH_RELEASE_ID`; los runs previos conservan su valor (0 reescrituras) |

## Entidades de dominio puro (sin tabla)

### BudgetPolicy / BudgetConsumption — `application/agent/budgets.py`

- `BudgetPolicy`: `window_hours` (default 24), `session_token_cap`, `user_token_cap`, `session_tool_call_cap`, `user_cost_cap_usd`, `user_concurrency_cap`, `warning_ratio` (default 0.8). Parametros de politica versionados via settings `AGENT_BUDGET_*` (Q3).
- `BudgetConsumption`: `session_tokens`, `user_tokens`, `session_tool_calls`, `user_cost_usd`, `active_user_runs` — computado de `AgentGraphRun`/`AgentNodeRun`/`AgentModelCall` × price table (R-09); 0 tabla de consumo (estado derivado).
- Verdictos: `ok` | `warning` | `exhausted`; `exhausted` → bloqueo duro recuperable (estado tipado `agent.budget_exhausted`, ventana o accion explicita, 0 degradacion de modelo).

### OpsDashboardReport — `application/agent_ops/`

Agregado de solo lectura derivado de `agent_graph_runs`/`agent_node_runs`/`agent_model_calls`/`agent_eval_suites`: `latency_p95`, `error_rate`, `tool_success_rate`, `interrupt_count`, `tokens_total`, `cost_total_usd`, `latest_eval_regressions` (vinculadas a su release y gate). `data_as_of` (antiguedad, FR-018). 0 PII: solo agregados y metadatos permitidos (FR-019).

## Ciclos de vida

- **EvalSuite**: `running` → `passed` | `blocked`. El gate corre con adapter simulado (Q4); `blocked` persiste `blocked_reasons` del veredicto de regresion (R-07).
- **GraphRelease**: entrada creada → `pending`; gate verde + regla de activacion (auto si determinista, `approved_by` si toca prompts/modelos) → `active`; problema detectado → entrada nueva `reverted` con motivo (FR-011); 0 mutaciones de entradas previas.
- **Presupuesto**: dentro → `warning` (ratio) → `exhausted` (bloqueo tipado) → recuperacion por ventana o accion explicita (FR-013/FR-014).

## Reglas de integridad y privacidad

- 0 PII en dataset, evals, dashboard y eventos: solo agregados, ids internos y metadatos permitidos (FR-003/FR-016/FR-018).
- `case_id`/`release_id` referencian contratos publicados; los parsers validan existencia (mismatch → `agent_evals.release_mismatch`).
- Inventario de tablas cerrado de `check-migrations.ps1` se actualiza con las 2 tablas nuevas (y la columna sobre tabla existente).
