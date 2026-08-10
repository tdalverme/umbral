# Research: Comportamiento conversacional y UI (H4.3)

**Feature**: 011-conversational-ui | **Date**: 2026-08-10

Decisions taken during planning. Each entry records the decision, the
rationale, and the alternatives considered.

## R-01 — Contratos de agente v3: state/topology/reply + intent schema; checkpoints v2 declarados incompatibles

**Decision**: Se crean `contracts/agent/v3/state-schema-v3.json`,
`graph-topology-v3.json`, `reply-schema-v3.json` e `intent-schema-v3.json`
(los archivos v1/v2 quedan intactos como versiones auditadas). Cambios
minimos sobre v2:

- `state-schema-v3`: puebla `intent` (declarado en v2 como "always null in
  v2, H4.3 fills it"), agrega `clarification` (`pending_params`, `rounds`) y
  documenta `pending_action` poblado (`{kind: "proposal", proposal_id}`)
  antes de cada interrupcion HITL.
- `graph-topology-v3`: nodos `start → compile_intent → (clarify |
  generate_reply → run_tools loop → require_confirmation [interrupt] →
  resolve_decision) → persist_reply`; `"interrupts": ["proposal_decision"]`.
- `reply-schema-v3`: `refs` con entity en `{listing, criterion,
  evidence_ref, proposal}` y limite `AGENT_REPLY_MAX_REFS`; `tool_calls`
  validados contra la politica por intencion (R-02).
- `intent-schema-v3`: salida estructurada de compilacion: `intent`
  (`consulta`/`refinamiento`/`comparacion`/`feedback`/`fuera_de_alcance`),
  `parameters[]` (key, value, confidence), `high_impact_missing[]`,
  `contradictions[]` (key, current_value, requested) y `allowed_tools` por
  intencion (politica determinista).

Los checkpoints v2 se declaran incompatibles con error tipado
(`AgentStateIncompatible`) al reanudar, consistente con R-02 de H4.2: los
checkpoints son estado operativo de ventana corta y una migracion v2→v3
seria especulativa.

**Rationale**: FR-001/FR-005 (schema versionado y serializable) y el
patron de versionado aceptado en H4.1/H4.2 (contratos por capa; los runs
registran versiones).

**Alternatives considered**: mutar v2 in-place: rechazado (runs previos
registran versiones, principio II/V). Migrar checkpoints v2→v3: rechazado
(ventana corta, migracion especulativa sin driver de producto).

## R-02 — Compilacion de intencion: nodo inicial + politica intent→tools enforceable

**Decision**: Un nodo `compile_intent` al inicio del graph produce la
salida estructurada de `intent-schema-v3` via `gateway.generate_structured`
(version de prompt `agent-intent-v1`). La politica `allowed_tools` del
contrato se aplica de forma DETERMINISTA en `generate_reply`/`run_tools`:
todo `tool_calls` generado se valida contra las tools permitidas de la
intencion compilada; una violacion produce error tipado en `tool_results`,
0 ejecucion y una respuesta grounded de limite. La clasificacion queda
registrada en el graph run (version de schema/prompt). 0 texto a SQL,
ranking o mutaciones: las unicas acciones posibles son las tools permitidas
de la intencion.

**Rationale**: FR-001/FR-002 (clasificacion auditada; 0 texto directo a
SQL/ranking/mutaciones). El enforcement determinista no depende del LLM y
se prueba en la suite de abuso v3 sin regresiones sobre la de H4.2.

**Alternatives considered**: confiar en el prompt para elegir tools:
rechazado — el guardrail debe ser codigo, no instruccion. Routing por nodo
por intencion: rechazado — acopla la topologia al catalogo de intenciones.

## R-03 — Aclaraciones como loop conversacional en estado (sin interrupt); templates deterministas

**Decision**: Las aclaraciones de alto impacto (UM-H4-018) NO usan el
mecanismo de interrupt: viven en el estado como `clarification`
(`pending_params`, `rounds`) y la respuesta del usuario se integra en el
siguiente turno (cada mensaje es un turno nuevo, H4.1). Disparo por
politica: parametros de alto impacto (budget, zona, hard filters, radio)
con confianza < `AGENT_CLARIFICATION_MIN_CONFIDENCE`, ausentes pero
necesarios, o contradiccion con el snapshot del perfil en contexto. Las
preguntas se generan con templates deterministas por parametro (0
variabilidad LLM, redactadas y probables). `rounds` se acota a
`AGENT_CLARIFICATION_MAX_ROUNDS` (2); al superarlo, respuesta grounded que
declara que no puede aplicar el cambio y sugiere la UI estructurada
(FR-008). La decision de aclarar/confianza queda registrada por turno en el
run (FR-009).

**Rationale**: FR-006..FR-010. El loop en estado reutiliza el runtime
existente (streaming/reanudable) sin maquinaria nueva de interrupt; los
templates deterministicos hacen la politica testeable sin LLM.

**Alternatives considered**: aclaraciones via interrupt con command:
rechazado — dos mecanismos de pausa distintos para el mismo patron de
"preguntar y esperar"; el interrupt queda reservado a la confirmacion de
mutaciones (R-04). Preguntas generadas por LLM: rechazado — variabilidad e
injection innecesarias para un formulario acotado.

## R-04 — HITL via LangGraph interrupt + Command(resume); decisiones como operacion explicita

**Decision**: La confirmacion de propuestas (UM-H4-019) usa `interrupt()`
de LangGraph: tras crear la propuesta, el nodo `require_confirmation`
escribe `pending_action = {kind: "proposal", proposal_id}` en el estado,
interrumpe con payload tipado `{type: "proposal_decision", proposal_id,
diff, impact, expires_at}` y el run queda en estado `interrupted`. La
decision (aprobar/editar/rechazar) es una OPERACION EXPLICITA del contrato
(`POST .../runs/{run_id}/decision`) que reanuda el MISMO run con
`Command(resume=decision)` (0 repeticion de efectos: el claim por sesion y
el ledger de H4.1 lo garantizan). Validacion cruzada: el estado del run
(`pending_action`) debe referenciar la propuesta de la decision; sin
interrupt esperando → `agent.no_pending_interrupt`; enviar un mensaje
mientras espera → `chat.decision_pending` con el payload de la interrupcion
(la UI muestra los controles de decision y deshabilita el composer).

**Rationale**: FR-011..FR-016 (decision sobre el mismo checkpoint, 0
duplicados, espera con ventana = TTL de propuesta). Decidir por operaciones
estructuradas es determinista, auditable (proposal row + run) y elimina el
riesgo de que el LLM parsee mutaciones desde texto libre.

**Alternatives considered**: aprobaciones parseadas del texto del chat
("dale, aprobala"): rechazado — mutacion critica dependiente de
clasificacion LLM, riesgo de misclasificacion y complejidad de test; el
conjunto de intenciones del spec no incluye "decision". Rechazo solo lazy
(al vencer): rechazado — FR-013 exige transicion interactiva con motivo.

## R-05 — Transiciones interactivas sobre la propuesta durable; edicion = propuesta derivada (clarificacion Q2)

**Decision**: `rejection_reason` del dominio se extiende a
`{obsolete, expired, user, edited}` y la tabla gana `rejection_note`
(texto acotado del usuario, nunca en eventos ni salidas redactadas) y
`superseded_by_proposal_id` (FK self, cadena de edicion). Transiciones:

- Rechazo interactivo: `pending → rejected('user')` con `rejection_note`
  opcional (FR-013); 0 efectos en el perfil.
- Edicion (clarificacion Q2, FR-014): `pending → rejected('edited')` con
  `superseded_by_proposal_id` apuntando a la NUEVA propuesta derivada
  (diff corregido validado por el mismo camino de `RadarService`), que
  nace `pending`, emite `search_profile.update_proposed.v1` y vuelve a
  interrumpir para confirmacion. La original JAMAS se muta (0 reescrituras);
  un solo uso y trazabilidad completa.

Migration `0011_chat_streaming`: agrega `superseded_by_proposal_id` +
indice, `rejection_note` y (si la columna esta restringida al implementar)
amplia el dominio de `rejection_reason`. 0 nuevos eventos de producto: los
rechazos/decisiones se auditan en filas + runs; la derivacion emite el
evento `update_proposed` existente (consistente con R-09 de H4.2).

**Rationale**: Clarificacion Q2 y FR-013/FR-014; el patron de objeto
inmutable + cadena derivada conserva la auditoria completa sin mutaciones.

**Alternatives considered**: edicion in-place con versionado de diff:
rechazado por la clarificacion Q2 (0 reescrituras). Descarte y
reproposicion desde cero: rechazado — pierde la base del diff previo.

## R-06 — Idempotencia de envio: chat_messages.client_message_id (indice unico parcial)

**Decision**: `append_user_message` acepta `client_message_id` (UUID del
cliente); la columna nueva `chat_messages.client_message_id` (nullable)
tiene indice unico parcial `uq_chat_messages_session_client (session_id,
client_message_id) WHERE client_message_id IS NOT NULL`. Replay con la
misma clave: devuelve el mensaje registrado, 0 duplicados y 0 runs nuevos.
Sin clave: comportamiento actual (FR-024, SC-005).

**Rationale**: FR-024 exige envio reenviable sin duplicar; patron identico
a la idempotencia de apply (H4.2 R-05) y de feedback (H3.3).

**Alternatives considered**: fingerprints separados: rechazado — el mensaje
es el objeto durable; anclar la clave ahi es el minimo.

## R-07 — Streaming SSE sobre RuntimeEvent; chunking deterministico del reply

**Decision**: El transporte del streaming es SSE (`text/event-stream`):
`POST /messages`, `POST /resume` y `POST /decision` devuelven un stream de
eventos tipados definidos en `contracts/chat/v1/streaming-events-v1.json`:
`chat.run_started`, `chat.reply_fragment`, `chat.tool_activity`,
`chat.interrupt_waiting`, `chat.run_completed`, `chat.run_failed`,
`chat.run_interrupted`, con envelope `event:<type>\nid:<seq>\ndata:<json>`.
El proveedor de modelo es request/response (adapter de H4.1): el nodo
`generate_reply` emite `ReplyFragment` particionando el texto de la
respuesta en fragmentos deterministicos por palabra
(`AGENT_REPLY_CHUNK_WORDS`, default 8): la UI renderiza progresivamente
sin delay artificial. El streaming por token del proveedor queda diferido
al ADR de proveedor (H4.4, UM-H4-004).

**Rationale**: FR-023/FR-026 (eventos tipados distinguibles; streaming con
indicacion de actividad). SSE reutiliza infra ya generada en el cliente web
(`core/serverSentEvents.gen.ts`), evita WebSockets (0 necesidad) y el
chunking deterministico entrega progresividad sin acoplar al proveedor.

**Alternatives considered**: WebSockets: rechazado — sobre-ingenieria para
turnos request/response; el runtime ya es reanudable. Streaming real del
proveedor: rechazado — dependencia de provider y del ADR de H4.4; el
contrato de eventos no cambia cuando llegue.

## R-08 — Contrato HTTP de chat: router nuevo, errores tipados, acciones de acceso

**Decision**: `src/umbral/api/routers/chat.py` expone (aditivo al OpenAPI
v1, cliente regenerado con `npm run api:generate`):

- `POST /api/v1/chat/sessions` — crear sesion `{search_profile_id}`.
- `GET /api/v1/chat/sessions?search_profile_id=` — listar sesiones del
  radar (el panel reanuda la ultima activa o crea, clarificacion Q3).
- `GET /api/v1/chat/sessions/{session_id}` — estado de la sesion.
- `GET /api/v1/chat/sessions/{session_id}/messages?limit&before_message_id`
  — historial paginado en orden (FR-021).
- `POST /api/v1/chat/sessions/{session_id}/messages` — enviar
  `{text, client_message_id, context?}` → SSE (R-07/R-06).
- `POST /api/v1/chat/sessions/{session_id}/resume` — reanudar el ultimo
  run interrumpido de la sesion (reconexion) → SSE.
- `POST /api/v1/chat/sessions/{session_id}/runs/{run_id}/decision` —
  `{kind: approve|reject|edit, change?, reason?, idempotency_key}` → SSE
  (R-04/R-05).

Errores tipados problem+json (convencion RFC 9457 existente) con codigos
`chat.*` (session_not_found, session_not_active, decision_pending,
execution_in_progress, message_too_long, content_invalid) y `agent.*`
(no_pending_interrupt, state_incompatible, run_not_found). Acciones de
acceso nuevas en `domain/identity/policy.py`: `product.chat.session.create/
read`, `product.chat.message.write`, `product.chat.decision.write` (mismo
patron deny-by-default con `resource_owner_id`, 0 acceso cruzado con ids
manipulados).

**Rationale**: FR-021/FR-022/FR-025 (contratos tipados con errores y
permisos; cliente regenerado). El router traduce ChatError/AgentError a
Problem con el patron `_problem_for` de los routers existentes.

**Alternatives considered**: WebSockets: rechazado (R-07). Paginacion por
offset: rechazado — cursor `before_message_id` es estable ante mensajes
nuevos (convencion de matches).

## R-09 — Propuestas de agente visibles y accionables desde la UI estructurada

**Decision**: `GET /api/v1/search-profiles/{search_profile_id}/
update-proposals?state=` lista las propuestas de cambio (nuevo metodo de
aplicacion `SearchProfileUpdateProposals.list`) incluyendo `session_id`,
`waiting_run_id` (el run interrumpido que espera decision, si hay) y
`superseded_by_proposal_id`. El banner del radar (FR-033) las muestra con
diff y acciones; las acciones usan el MISMO endpoint de decision de chat
(resuelto con session_id + run_id del listado). 0 divergencias entre vistas
y 0 segundo surface de decision.

**Rationale**: FR-033 exige propuestas pendientes visibles/accionables en
la UI estructurada con el mismo estado; un solo surface de decision evita
dos caminos de mutacion.

**Alternatives considered**: endpoint de decision sobre la propuesta sin
run: rechazado — violaria el HITL sobre checkpoint (FR-011).

## R-10 — Composicion de produccion del runtime (FR-042, cierre del follow-up diferido de H4.1)

**Decision**: `api/dependencies.py` extiende `RuntimeDependencies` con el
stack conversacional: gateway (managed en prod / fake en local segun
`agent_model_provider`), saver Postgres del checkpointer, `ToolExecutor`,
graph v3 y `ChatRuntime`; `RuntimeCompositionFactories` se extiende y los
duties de workers existentes (purge/expire) quedan coherentes. Verificacion
E2E: `tests/integration/api/test_chat_e2e.py` levanta la app real
(TestClient) con testcontainers + fake gateway y recorre el flujo completo
por HTTP: send → stream de eventos → propose → interrupt_waiting →
decision approve → apply → recomputacion, con el OpenAPI exportado
verificado (FR-042).

**Rationale**: FR-042 cierra el follow-up de H4.1 (composicion de
produccion del runtime); hasta hoy `build_agent_stack_v2` no esta cableado
en ningun root productivo.

**Alternatives considered**: dejar la composicion solo en workers:
rechazado — el runtime conversacional es superficie de la API (FR-021).

## R-11 — Web chat: hook propio sobre fetch+SSE; panel unico en la pagina del radar (clarificacion Q3)

**Decision**: La web NO adopta TanStack Query para el chat (las paginas
existentes usan fetch manual + `reloadKey`; el QueryClient montado sigue
inerte). Se construye `lib/chat/client.ts` (chatApi: sessions, history,
send, resume, decision) y `lib/chat/use-chat-stream.ts` (hook de estado del
panel: mensajes, status, reconnection SSE con `Last-Event-ID`, dedupe por
event id). Componentes: `ChatPanel` (raiz del panel, montado en
`radar/[id]`: al abrir reanuda la ultima sesion activa del radar o crea una
nueva, "conversacion nueva" desde el mismo panel, 0 rutas dedicadas),
`MessageList` (scroller con jump-to-latest y paginacion hacia atras),
`MessageItem`/`Bubble` (por rol, refs como MiniCard), `Composer` (textarea:
Enter envia, Shift+Enter nueva linea; deshabilitado durante ejecucion o
espera de decision), `StreamStatus` (estados con live region),
`MiniCard` (listing → link al radar/detalle) y `ProposalCard` (diff +
aprobar/editar/rechazar → endpoint de decision). Primitives shadcn
(proxima a `components.json`, style vega) se agregan via el CLI del
registry cuando se necesiten (scroll-area/textarea), siguiendo el patron
de los 7 primitivos existentes.

**Rationale**: FR-026..FR-030 y clarificacion Q3 (panel unico, teclado,
lectores de pantalla, contenido permitido). Consistencia con el patron de
fetch manual del codebase evita introducir un segundo patron de datos en
paralelo al cliente `radarApi` existente.

**Alternatives considered**: adoptar TanStack Query + cliente generado en
el chat: rechazado — mezclaria dos convenciones de datos; el contrato SSE
no es cacheable con query keys. Navegacion dedicada `/radar/[id]/chat`:
rechazado por la clarificacion Q3.

## R-12 — BFF web: route handlers de chat + forwardStream sin buffer

**Decision**: Nuevos route handlers en `src/app/api/radar/chat/*` que
siguen el patron BFF existente (Cookie + `X-Umbral-BFF-Token` +
`X-Correlation-ID`): `sessions` (GET list, POST create),
`sessions/[sessionId]` (GET), `sessions/[sessionId]/messages` (GET history,
POST send → SSE), `sessions/[sessionId]/resume` (POST → SSE),
`sessions/[sessionId]/runs/[runId]/decision` (POST → SSE). Se agrega
`forwardStream` en `lib/radar/server.ts` que pipea el body del upstream sin
bufferizar (`response.body` → `ReadableStream`, headers
`text/event-stream`), preservando el patron de los otros forwarders. El
proxy (`src/proxy.ts`) y la autenticacion de sesion no cambian.

**Rationale**: FR-021/FR-022 (contratos tipados de chat consumidos por la
web); el BFF es la unica superficie que la web toca (0 llamadas directas a
la API privada).

**Alternatives considered**: consumir la API privada desde el cliente
browser: rechazado — rompe el boundary del BFF y expone el token.

## R-13 — Reconexion e interrupcion: estados visibles, resume idempotente, 0 duplicados

**Decision**: El hook distingue los estados del turno (enviando, ejecutando,
esperando confirmacion, reanudando, fallo, completado) y los renderiza en
`StreamStatus` con `aria-live` (FR-035). Desconexion durante la generacion:
el SSE cliente reconecta y, al terminar la conexion (Last-Event-ID agotado),
llama `POST /resume` que reanuda el ultimo run interrumpido y reemite los
eventos restantes (0 repeticion de efectos por el claim por sesion);
mientras tanto la UI muestra "reanudando" y 0 fragmentos parciales se
persisten como mensaje final (solo respuestas completas, H4.1). Error
parcial: estado de fallo en el mensaje con retry idempotente
(`client_message_id` reutilizado, R-06). Ejecucion en curso en otra pestana:
estado tipado `execution_in_progress` con opcion de seguir la misma
ejecucion o esperar (FR-038).

**Rationale**: FR-035..FR-038 y SC-008. La reconexion reutiliza el claim
por sesion de H4.1: reanudar un run ya en curso devuelve el mismo run (0
paralelos, 0 duplicados).

**Alternatives considered**: re-streaming cross-tab de una ejecucion en
curso: rechazado — el contrato ya reanuda; la suscripcion multi-cliente es
H4.4+/sin driver.

## R-14 — Validacion de refs grounded al persistir

**Decision**: En `persist_reply` (v3), cada `ref` del mensaje assistant se
resuelve contra el search scope de la sesion: `{entity, id}` debe
referenciar un objeto de producto real y perteneciente al radar de la
sesion (listing, criterion, evidence_ref, proposal). Ref no resuelta o
ajena: error tipado → reintento acotado; si persiste, la respuesta se
persiste declarando la evidencia faltante (FR-017/FR-018). Las tools de
explicacion/comparacion ya devuelven evidencia persistida (H3.2/H4.2); las
refs se pueblan desde tool results redactados, nunca inventadas por el
modelo.

**Rationale**: FR-017..FR-020 (100% de afirmaciones con citas verificables;
0 citas ajenas). El punto de enforcement determinista es el persist:
resolver la ref es validable sin LLM.

**Alternatives considered**: confiar en que el modelo emita refs validas:
rechazado — sin validacion al persistir las citas rotas llegarian al
historial. Alucinar refs al renderizar: rechazado — 0 inventos (principio II).

## R-15 — Telemetria FR-043: primer fragmento y errores de streaming desde la web

**Decision**: La web mide y emite (via `lib/observability/telemetry.ts`
existente, campos seguros, 0 PII): `chat.first_fragment_ms` (tiempo hasta
el primer `chat.reply_fragment`) y `chat.stream_error` (con `error_code`).
Backend: sin telemetria nueva — latencia/uso ya quedan en graph/node runs
(H4.1) y tool runs (H4.2). Los budgets de performance (first-token,
Web Vitals) se fijan en UM-H6-017, no en este incremento.

**Rationale**: FR-043 exige medir y exponer para alimentar H6-017; el lib
de telemetria web ya existe y cumple el filtro de campos seguros.

**Alternatives considered**: instrumentar el backend con spans nuevos:
rechazado — latencia y errores ya estan en runs; el primer fragmento es una
medida de extremo a extremo del cliente.

## R-16 — Sin eventos de producto nuevos; auditoria en filas + runs

**Decision**: 0 tipos nuevos en `contracts/events/v1/events-registry.json`.
Rechazos interactivos, ediciones y decisiones se auditan en
`search_profile_update_proposals` (estado, motivo, nota, cadena
superseded) + `agent_node_runs`/`agent_graph_runs` con correlacion. La
derivacion por edicion emite el evento existente
`search_profile.update_proposed.v1` y la aplicacion el existente
`search_profile.update_applied.v1`. Consistente con R-09 de H4.2 (el ciclo
de propuestas ya tiene sus eventos; las transiciones internas son estado de
la fila).

**Rationale**: DoD de auditoria (principio V) sin duplicar eventos por
transicion; evita ensuciar el registry con tipos de baja senal.

**Alternatives considered**: evento por decision (`proposal.decided.v1`):
rechazado — la fila + el run ya son trazables; el registro de eventos es
para cambios de producto que otros sistemas consumen.

