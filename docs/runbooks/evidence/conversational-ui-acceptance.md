# Evidence: conversational-ui acceptance (H4.3)

**Feature**: 011-conversational-ui | **Date**: 2026-08-10 | **Branch**: `main`

Estado de cierre local del incremento `conversational-ui` (Épica H4.3,
UM-H4-017 a UM-H4-025). Spec: `specs/011-conversational-ui/spec.md`; plan:
`specs/011-conversational-ui/plan.md`; tareas: `specs/011-conversational-ui/tasks.md`
(59/65 completadas; commits `ab5a0e6` y `729da9e`).

## Resumen del incremento

- **Contratos de agente v3** (`state/graph/reply/intent-schema-v3.json`) y
  **contrato de streaming events** (`contracts/chat/v1/streaming-events-v1.json`):
  taxonomía de intención (consulta/refinamiento/comparacion/feedback/
  fuera_de_alcance) con política determinista `allowed_tools`; checkpoints v2
  declarados incompatibles (R-01/R-02).
- **Compilación de intención y aclaraciones** (`src/umbral/agent/intent/`):
  compiler vía structured output, policy determinista (0 SQL/ranking/
  mutaciones fuera de política) y aclaraciones de alto impacto con templates
  deterministas y rounds acotados (`AGENT_CLARIFICATION_*`) (R-02/R-03).
- **Human-in-the-loop** (UM-H4-019): `interrupt()` + `Command(resume)` en el
  runtime v3; decisiones approve/reject/edit como operaciones explícitas;
  rechazo interactivo (`rejected('user')` + nota) y edición como propuesta
  derivada (`rejected('edited')` + `superseded_by_proposal_id`, 0
  reescrituras) sobre la propuesta durable (R-04/R-05, clarificación Q2).
- **Respuestas grounded** (UM-H4-020): `refs` con entity {listing, criterion,
  evidence_ref, proposal}, cap `AGENT_REPLY_MAX_REFS`, validadas contra el
  scope al persistir (0 refs ajenas/inventadas) (R-14).
- **Contrato HTTP de chat streaming** (UM-H4-021): `api/routers/chat.py`
  (sesiones, historial con cursor, send/resume/decision con SSE sobre
  `RuntimeEvent`, listado de update-proposals), errores tipados problem+json,
  acciones `product.chat.*`; idempotencia de envío con
  `chat_messages.client_message_id` (migración `0011_chat_streaming`);
  OpenAPI exportado y cliente web regenerado (R-06/R-08).
- **UI web** (UM-H4-022..024): panel único en la página del radar (Q3),
  `lib/chat/*` (cliente + hook SSE con dedupe/reconexión), componentes
  ChatPanel/MessageList/MessageItem/Composer/StreamStatus/MiniCard/
  ProposalCard, BFF `/api/radar/chat/*` + `forwardStream`, banner de
  propuestas con la misma superficie de decisión, entrada contextual desde el
  detalle (`?chat_context=listing:<id>`) (R-11/R-12/R-13).
- **Suite de abuso v3 determinista** (T061) como gate y **harness**
  `scripts/check-chat.ps1` registrado en `check.ps1` (FR-041).

## Verificación

| Escenario quickstart | Resultado |
| --- | --- |
| 1. Conformance contratos v3 + streaming events | PASS (80 tests en suite no-Docker) |
| 2. Compilación de intención y política intent→tools | PASS |
| 3. Aclaraciones de alto impacto | PASS |
| 4. HITL: propose → interrupt → approve/reject/edit (runtime + edit chain) | PASS |
| 5. Respuestas grounded (refs scope + cap) | PASS |
| 6. Contrato HTTP de chat (router SSE sobre TestClient, errores tipados, decision_pending) | PASS |
| 7. E2E de composición con Postgres real (testcontainers) | PENDIENTE de ejecutar en este entorno (Docker daemon lento); escrito en `tests/integration/api/test_chat_e2e.py` |
| 8. Web: typecheck + lint + vitest | PASS (27/28; `runtime-routes.test.ts` pre-existente dependiente del entorno) |
| 9. Suite de abuso v3 + arquitectura + migración 0011 | PASS |

Comandos:

```powershell
$env:PYTHONPATH = "src"
uv run pytest tests/contract/test_agent_state_schema_v3.py tests/contract/test_agent_graph_topology_v3.py tests/contract/test_agent_reply_schema_v3.py tests/contract/test_agent_intent_schema_v3.py tests/contract/test_chat_streaming_contract.py tests/contract/test_chat_http_contract.py tests/unit/agent/intent tests/unit/agent/test_runtime_v3.py tests/unit/agent/test_grounding.py tests/unit/agent/test_abuse_suite_v3.py tests/unit/application/chat/test_message_idempotency.py tests/unit/application/agent/tools/test_proposal_transitions.py tests/unit/config/test_agent_settings.py tests/integration/chat/test_hitl_lifecycle.py tests/integration/chat/test_edit_chain.py tests/integration/chat/test_streaming_router.py tests/architecture/test_agent_boundaries.py tests/migrations/test_0011_chat_streaming.py -q
.\scripts\check-chat.ps1            # incluye test_chat_e2e (requiere Docker)
npm --workspace @umbral/web run typecheck
npm --workspace @umbral/web run lint
npm --workspace @umbral/web run test
```

La migración `0011_chat_streaming` se validó en
`tests/migrations/test_0011_chat_streaming.py` (determinista, sin Docker) y
se aplica al head en los tests de integración (alembic upgrade → head).

## Decisiones de clarificación aplicadas (sesión 2026-08-10)

1. La creación de búsquedas desde el chat queda fuera de alcance (Q1): sin
   radar activo, el chat dirige al onboarding estructurado.
2. Editar una propuesta crea una propuesta nueva derivada; la original pasa a
   `rejected('edited')` con `superseded_by_proposal_id` (Q2, 0 reescrituras).
3. El chat es un panel único integrado en la página del radar (Q3): reanuda
   la última sesión o crea una; 0 rutas dedicadas y 0 selector de sesiones.

## Diferidos a seguimiento

- Correr en CI los tests de integración que requieren Docker/testcontainers
  (el daemon Docker de este entorno quedó colgado para operaciones de
  contenedores): `tests/integration/api/test_chat_e2e.py` (T062, escrito y
  recogido correctamente), `test_update_proposals_list` (T047, cubierto a
  nivel unit) y los suites existentes; `check.ps1` completo desde checkout
  limpio y marcar UM-H4-017 a UM-H4-025 en `docs/product/backlog.md`.
- Tests web periféricos restantes (T055 segunda pestaña, T058 contextual
  vitest) y `test_send_replay.py` (T034; la idempotencia está garantizada a
  nivel de servicio y el `client_message_id` ya se hila por HTTP).
- Fallos pre-existentes ajenos a este incremento, dependientes del entorno:
  `runtime-routes.test.ts` (web, env de release manifest) y
  `test_supabase_adapter.py` (identity, último commit `fcda7ce`).
- ADR del proveedor de modelo y evals del graph (H4.4).
