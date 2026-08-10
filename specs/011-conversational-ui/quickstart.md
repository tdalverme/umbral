# Quickstart: Comportamiento conversacional y UI (H4.3)

**Feature**: 011-conversational-ui | **Date**: 2026-08-10

Validation guide. Implementation details live in `plan.md` and `tasks.md`.

## Prerequisites

- `.venv` activado y `uv sync --frozen --all-groups`.
- Postgres con PostGIS/pgvector accesible para la integración (testcontainers
  según la convención de `check-agent.ps1`).
- Migración `0011_chat_streaming` aplicada (`chat_messages.client_message_id`
  + `search_profile_update_proposals.rejection_note` /
  `superseded_by_proposal_id`).
- Web: `npm --workspace @umbral/web run api:generate` (cliente regenerado
  con los paths de chat) y `npm --workspace @umbral/web install` si se
  agregaron primitives shadcn.

## Escenarios

### 1. Conformance: contratos v3, intent y streaming events

```powershell
uv run pytest tests/contract/test_agent_state_schema_v3.py tests/contract/test_agent_graph_topology_v3.py tests/contract/test_agent_reply_schema_v3.py tests/contract/test_agent_intent_schema_v3.py tests/contract/test_chat_streaming_contract.py -q
```

Expected: PASS. Los schemas v3 son JSON-safe y versionados
(`AGENT_CHAT_STATE_SCHEMA_VERSION=3`, `AGENT_CHAT_TOPOLOGY_VERSION=3`); el
intent schema declara las 5 intenciones con `allowed_tools`; el contrato de
streaming expone los 7 tipos de evento con sus payloads (FR-001, FR-005,
FR-023).

### 2. Compilación de intención y política intent→tools

```powershell
uv run pytest tests/unit/agent/intent -q
```

Expected: PASS (determinista, sin LLM o con FakeModelGateway).

- Cada mensaje se clasifica en exactamente una intención del conjunto
  permitido y la clasificación queda registrada con versiones (FR-001).
- `tool_calls` fuera de `allowed_tools` de la intención → error tipado, 0
  ejecución y 0 efectos (FR-002).
- Intención fuera de alcance (incluida la creación de un radar: Q1) →
  respuesta que declara el límite y dirige al onboarding estructurado;
  0 invenciones (FR-004/FR-005).

### 3. Aclaraciones de alto impacto

```powershell
uv run pytest tests/unit/agent/intent/test_clarification.py -q
```

Expected: PASS.

- Parámetro de alto impacto (budget, zona, hard filters, radio) con
  confianza < `AGENT_CLARIFICATION_MIN_CONFIDENCE`, ausente pero necesario,
  o contradictorio con el perfil → aclaración con template determinista
  antes de cualquier propuesta; 0 adivinanzas (FR-006/FR-007).
- La respuesta del usuario se integra en el siguiente turno; al superar
  `AGENT_CLARIFICATION_MAX_ROUNDS` (2) se declara la imposibilidad y se
  sugiere la UI estructurada (FR-008).
- La decisión de aclarar y su confianza quedan registradas por turno
  (FR-009).

### 4. Human-in-the-loop: aprobar, editar, rechazar

```powershell
uv run pytest tests/integration/chat/test_hitl_lifecycle.py tests/integration/chat/test_edit_chain.py tests/unit/application/agent/tools/test_proposal_transitions.py -q
```

Expected: PASS. Con Postgres (testcontainers):

- `propose` → el graph interrumpe (`chat.interrupt_waiting` con proposal_id,
  diff, impacto y expiración) y el run queda `interrupted`; enviar un
  mensaje mientras espera → `chat.decision_pending` (FR-011, R-04).
- Aprobar → reanuda el MISMO run y aplica con confirmación e idempotency
  key: perfil versionado, propuesta `approved` de un solo uso y
  recomputación que preserva el run anterior (FR-012, H4.2).
- Rechazar → `rejected('user')` con `rejection_note` opcional, 0 efectos en
  el perfil y 0 reaplicación (FR-013).
- Editar → propuesta NUEVA derivada con el diff corregido; la original pasa
  a `rejected('edited')` con `superseded_by_proposal_id` (0 reescrituras,
  Q2/FR-014) y el run vuelve a interrumpir esperando confirmación de la
  derivada.
- Decisión sobre run sin interrupt o con propuesta distinta a la esperada →
  `agent.no_pending_interrupt` / `agent.decision_mismatch`, 0 efectos.
- Replay con la misma idempotency key → 0 duplicados (H4.2 R-05).

### 5. Respuestas grounded

```powershell
uv run pytest tests/unit/agent/intent tests/unit/application/agent -q
```

Expected: PASS. Ref no resoluble o ajena al search scope → reintento acotado
y, si persiste, la respuesta se persiste declarando la evidencia faltante;
0 citas rotas o ajenas (FR-017..FR-020, R-14).

### 6. Contrato HTTP de chat streaming

```powershell
uv run pytest tests/contract/test_chat_http_contract.py tests/integration/chat/test_streaming_router.py tests/integration/chat/test_send_replay.py -q
.\scripts\export-openapi.ps1
npm --workspace @umbral/web run api:check
```

Expected: PASS.

- Crear sesión, listar sesiones del radar, estado, historial paginado con
  cursor `before_message_id` (FR-021).
- Enviar mensaje → stream SSE con eventos tipados distinguibles; reintento
  con el mismo `client_message_id` → 0 mensajes duplicados y 0 runs nuevos
  (FR-023/FR-024).
- Errores tipados: sesión inexistente, pausada/archivada, ejecución en
  curso, `decision_pending`, contenido fuera de límites (FR-022).
- Acceso: ids manipulados de sesión/run/propuesta → denegados en el 100%
  de los casos (0 acceso cruzado, acciones `product.chat.*`).
- El OpenAPI re-exportado y el cliente web regenerado no muestran drift.

### 7. Composicion de produccion y E2E (FR-042)

```powershell
uv run pytest tests/integration/api/test_chat_e2e.py -q
```

Expected: PASS. La app real (TestClient) con testcontainers + fake gateway
recorre el flujo completo por HTTP: send → stream → propose →
interrupt_waiting → decision approve → apply → recomputación preservando el
run anterior, con el stack compuesto en `api/dependencies.py`.

### 8. Web: panel de chat accesible

```powershell
npm --workspace @umbral/web run test
npm --workspace @umbral/web run lint
npm --workspace @umbral/web run typecheck
```

Expected: PASS. Componentes con teclado (Enter envía, Shift+Enter nueva
línea), roles y live regions para estados y streaming, jump-to-latest,
mini-cards enlazadas al radar/detalle, proposal card con aprobar/editar/
rechazar (FR-026..FR-034).

### 9. Suite de abuso v3 (gate) y harness completo

```powershell
uv run pytest tests/unit/agent/test_abuse_suite_v3.py -q
.\scripts\check-chat.ps1
.\scripts\check.ps1
```

Expected: PASS en los tres. Violaciones de política de intención, bypass de
aclaración, abuso de decisiones, replay de envío y acceso cruzado en
endpoints de chat → 0 efectos en el 100% de los casos, determinista y sin
LLM (FR-041). `check-chat.ps1` queda registrado en `check.ps1`.

## Verificación final

- Cerrar con `.\scripts\check.ps1` en verde desde checkout limpio y
  registrar evidencia consolidada en
  `docs/runbooks/evidence/conversational-ui-acceptance.md`, incluyendo los
  9 escenarios de este quickstart, el diff de
  `contracts/openapi/v1/openapi.json` (aditivo) y el estado del registry de
  eventos (sin cambios, R-16).
