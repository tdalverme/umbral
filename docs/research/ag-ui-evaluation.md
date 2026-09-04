# Evaluacion de AG-UI para Umbral

**Fecha:** 2026-08-22  
**Alcance:** protocolo AG-UI, SDKs oficiales, integracion oficial con LangGraph/FastAPI y CopilotKit como cliente de referencia. Solo se usaron fuentes primarias.

## Veredicto

**No conviene implementar AG-UI ahora como reemplazo del transporte conversacional de Umbral.** El beneficio incremental seria bajo y la migracion tocaria una superficie ya implementada, especifica del producto y cubierta por contratos: sesiones durables, historial, SSE, reconexion, HITL, autorizacion, BFF y componentes React. AG-UI aportaria sobre todo interoperabilidad y SDKs de cliente; hoy Umbral no tiene un segundo cliente, canal o framework que necesite esa interoperabilidad.

La decision no es "descartar AG-UI". La opcion razonable es **mantenerlo como protocolo de borde candidato** y reconsiderar un adaptador compatible cuando exista un driver concreto: un segundo frontend/canal, integracion con un cliente externo, generative UI controlada o un costo comprobado de mantener el reducer SSE propio. En ese escenario conviene traducir eventos en el borde, no reemplazar el dominio, la persistencia, las tools ni el runtime de Umbral.

## Que es y que no es

AG-UI es un protocolo abierto, liviano y orientado a eventos para conectar agentes con aplicaciones. Define input de ejecucion, eventos de ciclo de vida, mensajes, tool calls y estado; no reemplaza LangGraph, el dominio ni la persistencia de producto. Su arquitectura es agnostica del transporte y soporta SSE, WebSockets y otros medios ([arquitectura oficial](https://docs.ag-ui.com/concepts/architecture), [repositorio oficial](https://github.com/ag-ui-protocol/ag-ui)).

El contrato de entrada actual incluye `threadId`, `runId`, `state`, `messages`, `tools`, `context`, `forwardedProps` y `resume`; el frontend y el backend intercambian una secuencia estandar de eventos ([schema oficial de `RunAgentInput`](https://github.com/ag-ui-protocol/ag-ui/blob/main/sdks/typescript/packages/core/src/types.ts)). Los eventos cubren lifecycle, texto, tools, snapshots/deltas de estado, actividad, razonamiento y extensiones custom ([schema oficial de eventos](https://github.com/ag-ui-protocol/ag-ui/blob/main/sdks/typescript/packages/core/src/events.ts), [documentacion de eventos](https://docs.ag-ui.com/sdk/js/core/events)).

CopilotKit no es sinonimo de AG-UI: es un stack/UI cliente construido sobre el protocolo. Suma componentes de chat, generative UI, shared state y HITL, pero adoptarlo agrega una capa de producto y dependencias mayor que adoptar solo los tipos o el cliente de AG-UI ([repositorio oficial de CopilotKit](https://github.com/CopilotKit/CopilotKit)).

## Estado observable de madurez y adopcion

La señal positiva es clara:

- El repositorio oficial muestra actividad alta, aproximadamente 15.5k estrellas, 1.4k forks y mas de 3.300 commits al momento de esta evaluacion; esto prueba interes y mantenimiento, no por si solo uso productivo ([repositorio oficial](https://github.com/ag-ui-protocol/ag-ui)).
- La matriz oficial lista soporte para LangChain/LangGraph y varias integraciones first-party o asociadas: Google ADK, Microsoft Agent Framework, AWS Strands, Mastra, PydanticAI, LlamaIndex y otras ([matriz oficial](https://github.com/ag-ui-protocol/ag-ui#-supported-integrations)).
- Hay integracion Python oficial `ag-ui-langgraph` con helper para FastAPI, traduccion de mensajes y streaming de eventos ([README oficial de la integracion](https://github.com/ag-ui-protocol/ag-ui/tree/main/integrations/langgraph/python)).
- Los releases son frecuentes; por ejemplo, la integracion LangGraph `0.0.43` fue publicada el 2026-08-16 y el repositorio siguio publicando paquetes hasta el 2026-08-20 ([releases oficiales](https://github.com/ag-ui-protocol/ag-ui/releases)).

La señal de cautela tambien es concreta:

- Los paquetes relevantes siguen sin version estable: `@ag-ui/core` esta en `0.0.58`, `ag-ui-protocol` en `0.1.20` y `ag-ui-langgraph` en `0.0.43` en `main` ([package oficial TypeScript](https://github.com/ag-ui-protocol/ag-ui/blob/main/sdks/typescript/packages/core/package.json), [package oficial Python](https://github.com/ag-ui-protocol/ag-ui/blob/main/sdks/python/pyproject.toml), [package oficial LangGraph](https://github.com/ag-ui-protocol/ag-ui/blob/main/integrations/langgraph/python/pyproject.toml)). Versiones `0.x` y releases frecuentes sugieren una API todavia en movimiento.
- La propia integracion LangGraph mantiene dos caminos de resume. El outcome estructurado de interrupt es opt-in porque clientes CopilotKit `v1.60.x` aun usan el canal legacy y podrian dejar un run varado si se habilita prematuramente ([README oficial, seccion interrupts](https://github.com/ag-ui-protocol/ag-ui/tree/main/integrations/langgraph/python#resuming-via-ag-ui-standard-resume)).
- Hay bugs recientes y especificos de los invariantes que Umbral ya resolvio: duplicacion de `RUN_STARTED` en un flujo de interrupt ([issue oficial #1584](https://github.com/ag-ui-protocol/ag-ui/issues/1584)), deltas de estado que fallan al compactarse entre batches ([issue oficial #1720](https://github.com/ag-ui-protocol/ag-ui/issues/1720)) y fixes de integracion Python pendientes de un release estable de CopilotKit ([issue oficial #6231](https://github.com/CopilotKit/CopilotKit/issues/6231)). No implican que el proyecto sea inviable; si que el costo de pinning, pruebas de compatibilidad y upgrades seria real.
- La documentacion de arquitectura todavia resume el protocolo como "16 eventos", mientras el enum actual ya incluye mas familias y aliases deprecados que seran removidos en `1.0.0`; es una desincronizacion menor pero observable entre narrativa y schema canonico ([arquitectura oficial](https://docs.ag-ui.com/concepts/architecture), [enum oficial](https://github.com/ag-ui-protocol/ag-ui/blob/main/sdks/typescript/packages/core/src/events.ts)).
- El protocolo todavia no ofrece una operacion core claramente estable para hidratar historial/estado sin ejecutar el agente. Una propuesta oficial de `run_mode: "sync"` seguia en discusion y documenta que hoy se usan endpoints fuera del protocolo ([discusion oficial #1827](https://github.com/ag-ui-protocol/ag-ui/discussions/1827)). Umbral ya tiene reads explicitos de sesion e historial.

**Lectura honesta:** AG-UI tiene traccion y buenas probabilidades de consolidarse, pero hoy debe tratarse como una dependencia joven y evolutiva, no como un estandar estabilizado que automaticamente reduzca riesgo.

## Encaje con la arquitectura actual de Umbral

Umbral ya posee la mayor parte de las capacidades base que AG-UI estandariza:

- `src/umbral/api/routers/chat.py` expone sesiones, historial, send/resume/decision y SSE tipado.
- `apps/web/src/lib/chat/use-chat-stream.ts` mantiene el estado del panel, reconstruye historial, consume fragments, maneja errores y reanuda.
- `apps/web/src/components/chat/*` implementa el chat de producto, refs grounded y cards de propuestas.
- `specs/011-conversational-ui/contracts/chat-streaming-contracts-v1.md` fija el contrato; tests contractuales, de integracion y E2E cubren streaming e HITL.
- LangGraph ya aporta checkpoint, streaming e interrupts. Esas capacidades pertenecen al runtime y seguirian existiendo con o sin AG-UI ([streaming oficial de LangGraph](https://docs.langchain.com/oss/python/langgraph/streaming), [interrupts oficiales](https://docs.langchain.com/oss/python/langgraph/interrupts)).

Una traduccion conceptual es posible, pero no mecanica:

| Umbral hoy | AG-UI aproximado | Friccion |
|---|---|---|
| `chat.run_started` | `RUN_STARTED` | Baja; cambia el envelope y los IDs. |
| `chat.reply_fragment` | `TEXT_MESSAGE_START/CONTENT/END` | Media; Umbral no emite start/end por mensaje en el stream. |
| `chat.tool_activity` | `TOOL_CALL_START/ARGS/END/RESULT` o `ACTIVITY_*` | Alta; Umbral expone actividad redactada, no argumentos/resultados completos. Esto es deliberado y mas seguro. |
| `chat.interrupt_waiting` + endpoint `/decision` | `RUN_FINISHED.outcome.interrupt` + `RunAgentInput.resume[]` | Media/alta; la integracion oficial aun mantiene compatibilidad legacy. |
| `chat.run_completed` / `chat.run_failed` | `RUN_FINISHED` / `RUN_ERROR` | Baja. |
| `GET` historial | `MESSAGES_SNAPSHOT` | Media; falta una operacion core de sync sin run y Umbral necesita paginacion/ownership. |
| refs y `ProposalCard` | tool calls, custom events o UI generativa controlada | Media; AG-UI no define la semantica de vivienda ni la evidencia auditable. |

## Robustez comparada: implementacion actual vs. AG-UI

Esta comparacion toma como baseline **el codigo actual**, no solo los documentos de diseño. Tambien evita atribuirle al protocolo garantias que pertenecen a una implementacion: AG-UI estandariza inputs, eventos y su procesamiento; no implementa por si mismo autenticacion, persistencia durable, ownership ni idempotencia de efectos de negocio.

| Dimension | Umbral actual | AG-UI / integracion oficial | Veredicto para Umbral hoy |
|---|---|---|---|
| **Contrato** | Contrato estrecho y versionado para este producto: OpenAPI, JSON de eventos, errores tipados y schemas separados de estado/topologia/reply. Las propuestas, refs y decisiones tienen semantica explicita. | Contrato mucho mas amplio y portable, con tipos/schemas oficiales en TypeScript y Python, lifecycle completo y clientes reutilizables ([tipos](https://github.com/ag-ui-protocol/ag-ui/blob/main/sdks/typescript/packages/core/src/types.ts), [eventos](https://github.com/ag-ui-protocol/ag-ui/blob/main/sdks/typescript/packages/core/src/events.ts)). | **Empate con objetivos distintos.** AG-UI es mas robusto como wire protocol general; Umbral es mas preciso y enforceable para vivienda. Migrar no elimina las extensiones de dominio. |
| **Streaming** | SSE simple, legible y con eventos de producto acotados. El backend asigna secuencia monotona por conexion y no filtra args/resultados de tools. Pero el parser web ignora `id:`, descarta frames JSON invalidos silenciosamente y no implementa dedupe real; la reconexion es una accion manual. | Lifecycle de mensaje `START/CONTENT/END`, tool calls correlacionadas, snapshots y cliente/reducer estandar; el schema permite validar cada evento ([eventos oficiales](https://docs.ag-ui.com/sdk/js/core/events), [mensajes](https://docs.ag-ui.com/concepts/messages)). Tiene mas estados y complejidad, y existen bugs recientes de secuencia/compactacion. | **Ventaja AG-UI en el cliente y wire lifecycle.** La implementacion actual es suficiente en happy path, pero su promesa documental de dedupe/reconexion supera lo que hoy hace el codigo. |
| **HITL** | Proposal durable, `pending_action` en checkpoint, endpoint de decision con ownership, TTL, diff/impact, approve/reject/edit, idempotency key y validacion contra el mismo run. Hay tests de ciclo y cadena de edicion. | Modelo general de interrupts con IDs y `RunAgentInput.resume[]`, incluido soporte de multiples interrupts ([contrato oficial](https://docs.ag-ui.com/concepts/interrupts)). En LangGraph, el outcome canonico sigue opt-in por incompatibilidad con clientes legacy ([README oficial](https://github.com/ag-ui-protocol/ag-ui/tree/main/integrations/langgraph/python#resuming-via-ag-ui-standard-resume)). | **Ventaja Umbral para el caso real actual.** AG-UI es mas general, pero hoy agregaria traduccion y riesgo de compatibilidad sin mejorar la garantia de negocio. |
| **Durabilidad y replay** | Sesiones/mensajes son producto durable; checkpoints son estado operativo; runs y node/tool runs dejan auditoria. Solo persiste replies completos y hay ledger de efectos. | El protocolo ofrece snapshots/event streams serializables y branching, pero la durabilidad depende del host/framework. El adaptador LangGraph usa el checkpointer del graph; AG-UI no crea una fuente de verdad de producto. | **Ventaja Umbral.** Ya separa correctamente historia, producto, auditoria y checkpoint. AG-UI puede transportar esa proyeccion, no sustituirla. |
| **Auth y aislamiento** | Cookie de producto, BFF, acciones deny-by-default y ownership por usuario/sesion en cada operacion. Tools validan el scope del radar. | Intencionalmente fuera del core: `threadId`/`runId` correlacionan, pero el host debe autenticar, autorizar y vincular threads a usuarios. El helper FastAPI directo no incorpora las politicas de Umbral. | **Ventaja clara Umbral.** Un endpoint AG-UI solo seria aceptable detras del mismo Product API y access control. |
| **Idempotencia y concurrencia** | `client_message_id` con unicidad por sesion; una ejecucion no terminal por sesion; ledger `effects_applied`; mutaciones con keys e indices/repositories idempotentes; resume del mismo run. | El input lleva IDs de thread/run y el HITL moderno lleva interrupt IDs/resume, pero el protocolo no garantiza idempotencia de mensajes, tools ni efectos de negocio: la implementa cada agente/host. | **Ventaja clara Umbral.** Sus garantias son mas profundas que el envelope. Deben preservarse aun si se adopta AG-UI. |
| **Estado** | Checkpoint versionado y JSON-safe; estado conversacional separado de perfiles/listings/recomendaciones durables. La UI recibe solo proyecciones acotadas. | Shared state bidireccional con `STATE_SNAPSHOT` y `STATE_DELTA` JSON Patch ([estado oficial](https://docs.ag-ui.com/concepts/state)); es mas expresivo para UI reactiva, pero exige controlar tamaño, autoridad y resync. Existe un bug reciente del cliente al compactar deltas entre batches ([#1720](https://github.com/ag-ui-protocol/ag-ui/issues/1720)). | **Umbral es mas robusto en boundary; AG-UI es mas capaz en sincronizacion.** Solo conviene si aparece una UX que realmente necesite shared state, usando una proyeccion, nunca el checkpoint crudo. |
| **Tools** | Registry cerrado y versionado; input/output schema, timeout, limite de calls, allowlist por intencion, confirmacion, idempotencia, redaccion y 0 SQL libre. El stream expone solo nombre/status. | Lifecycle estandar de tool calls, streaming de args/resultados y frontend tools, excelente para observabilidad y generative UI ([tools oficiales](https://docs.ag-ui.com/concepts/tools)). No impone la politica de autoridad, redaccion o efectos del dominio. | **Ventaja Umbral en seguridad; AG-UI en expresividad UI.** Exponer args/resultados o confiar en tools anunciadas por el browser seria una regresion salvo proyeccion estricta. |
| **Interoperabilidad** | Un contrato privado para el frontend Next.js/BFF de Umbral. Todo consumidor nuevo debe implementar ese contrato. | Es el objetivo central: un mismo input/event stream, SDKs multi-lenguaje e integraciones oficiales para varios frameworks ([matriz oficial](https://github.com/ag-ui-protocol/ag-ui#-supported-integrations)). | **Ventaja clara AG-UI**, pero solo produce retorno cuando exista un segundo consumidor o necesidad de cambiar cliente/framework. |
| **Madurez operativa** | Superficie chica bajo control del equipo, con tests contractuales, integracion y E2E. Tambien tiene gaps entre spec y codigo en reconexion/dedupe/paginacion y un worker SSE sin manejo explicito de excepciones. | Ecosistema mayor, mas contributors e integraciones, pero paquetes `0.x`, releases frecuentes, docs/schema con churn y bugs recientes en el adaptador LangGraph. | **Sin ganador absoluto.** Umbral reduce riesgo externo y AG-UI reduce codigo propietario de protocolo. Hoy el churn de migrar es mayor que el riesgo de mantener la superficie actual, pero hay deuda local que debe corregirse independientemente. |

### Gaps observados en la implementacion actual

Estos puntos moderan el veredicto: no adoptar AG-UI no significa declarar al cliente actual completamente robusto.

1. **Dedupe SSE no implementado en el browser.** El contrato afirma dedupe por `(run_id, id)`, pero [`parseStream`](../../apps/web/src/lib/chat/client.ts) no conserva la linea `id:` y [`useChatStream`](../../apps/web/src/lib/chat/use-chat-stream.ts) no mantiene un set/cursor de eventos vistos.
2. **Reconexion no automatica.** El hook expone `resume()` y el panel ofrece retry manual, pero no envia `Last-Event-ID` ni reanuda automaticamente al terminar un stream incompleto. AG-UI ofrece un lifecycle/cliente mas rico, aunque la continuidad durable igualmente debe implementarse y probarse en el host.
3. **Frames invalidos se pierden silenciosamente.** El parser atrapa el error de `JSON.parse` y omite el frame. Eso evita estado parcial, pero puede convertir una violacion de contrato en una respuesta incompleta sin error observable. Un validador de schema/secuencia seria mas robusto.
4. **La paginacion publicada no esta materializada.** El endpoint acepta `limit` y `before_message_id`, pero el router actual devuelve todo `list_history`; AG-UI tampoco resuelve por si mismo la paginacion de producto.
5. **Terminacion del stream ante excepciones.** El worker de `_stream_turn` no envuelve `run_turn` en `try/finally`; una excepcion inesperada antes de `events.put(None)` puede dejar el consumidor esperando. Adoptar AG-UI no corrige automaticamente este fallo, pero su `RUN_ERROR` y validacion de lifecycle dan una convencion clara para cerrarlo.

### Conclusion de robustez

- **Backend y garantias de negocio:** Umbral es mas robusto hoy. Su durabilidad, ownership, idempotencia, tools y HITL estan ligados a objetos y politicas reales del producto.
- **Wire protocol y cliente de streaming:** AG-UI es mas robusto y completo. Tiene lifecycle granular, schemas reutilizables, reducers/clientes y mayor interoperabilidad.
- **Resultado neto:** no justifica una migracion. Si se quisiera capturar la principal ventaja de AG-UI, el camino es un adaptador de eventos o una mejora quirurgica del parser/reducer actual; no entregar el control del runtime o del estado de producto al protocolo.

### Donde si encaja bien

1. **Interoperabilidad futura.** Un adaptador permitiria conectar clientes AG-UI sin enseñarles el contrato privado de Umbral.
2. **Reducer y tipos estandarizados.** `@ag-ui/client` puede acumular mensajes/estado y validar secuencias, reduciendo parte del parser/reducer propio.
3. **UI generativa controlada.** Tool calls estandarizados podrian renderizar componentes preconstruidos, por ejemplo comparaciones o propuestas, manteniendo Umbral el control del layout ([tools oficiales](https://docs.ag-ui.com/concepts/tools)).
4. **Ecosistema LangGraph.** La integracion oficial ya convierte eventos de LangGraph y ofrece endpoint FastAPI, por lo que un spike de compatibilidad no partiria de cero ([integracion oficial](https://github.com/ag-ui-protocol/ag-ui/tree/main/integrations/langgraph/python)).

### Donde choca o aporta poco

1. **No elimina la logica dificil.** Ownership, sesiones durables, paginacion, idempotencia, rate limits, refs grounded, auditoria, propuestas y su lifecycle seguirian siendo de Umbral.
2. **Duplicaria o reemplazaria una superficie ya probada.** El ahorro de codigo aparece principalmente en el borde; el costo inicial es migrar contratos, BFF, hook, tests y reconexion.
3. **Shared state puede erosionar la fuente de verdad.** AG-UI permite estado bidireccional mediante snapshots y JSON Patch ([estado oficial](https://docs.ag-ui.com/concepts/state)). Umbral debe proyectar solo estado de UI; nunca exponer el checkpoint completo ni permitir que el cliente convierta estado conversacional en estado de producto.
4. **Frontend tools no deben ampliar autoridad.** `RunAgentInput.tools` permite anunciar tools desde el cliente. En Umbral, el Agent Orchestrator solo puede invocar tools internas explicitas y autorizadas. Adoptar AG-UI no debe convertir tools declaradas por el browser en capacidades confiables.
5. **Identidad y ownership siguen fuera del protocolo.** `threadId` y `runId` correlacionan ejecuciones, pero Umbral debe continuar vinculando cada sesion al principal autenticado y autorizando cada operacion; un ID de thread nunca puede funcionar como credencial.
6. **La integracion oficial agrega dependencias no deseadas.** `ag-ui-langgraph` depende de `langchain>=1.2.0`, `langchain-core`, un toolkit A2UI y LangGraph ([pyproject oficial](https://github.com/ag-ui-protocol/ag-ui/blob/main/integrations/langgraph/python/pyproject.toml)). Umbral hoy usa LangGraph con un gateway propio y deliberadamente evito adoptar la abstraccion de modelos de LangChain. Instalar el wrapper completo ensancharia el arbol de dependencias y el seam.
7. **El helper FastAPI no respeta automaticamente el Product API.** Montar el graph directo como `/agent` es simple en el ejemplo oficial, pero Umbral necesita pasar por autenticacion, autorizacion, servicios de aplicacion, persistencia de mensajes y auditoria. Usarlo sin una capa de traduccion violaria la direccion de dependencias del proyecto.
8. **CopilotKit tiene bajo retorno inmediato.** Los componentes actuales estan adaptados al radar, evidencia y propuestas. Sustituirlos por un chat generico perderia control de producto; conservarlos sobre CopilotKit agregaria una abstraccion adicional antes de demostrar un beneficio. Ademas, CopilotKit mantiene una migracion activa de frontend v1 a v2 ([guia oficial](https://docs.copilotkit.ai/migrate/v2)), otro costo de churn si se adopta la capa UI completa ahora.

## Costos y riesgos de adopcion

### Reemplazo completo ahora

- Rediseñar el POST de turnos al `RunAgentInput` estandar o agregar un nuevo endpoint.
- Cambiar el stream al lifecycle de mensajes/tool calls de AG-UI.
- Adaptar create/list/history y reconexion, que no quedan completamente cubiertos por el core.
- Reescribir o envolver `useChatStream`, BFF y tests contractuales/E2E.
- Definir una proyeccion segura de estado y redaccion de tool events.
- Agregar pinning estricto, pruebas de secuencia y una politica de upgrades para paquetes `0.x`.
- Resolver la convivencia entre el endpoint estructurado de decision de Umbral y `resume[]`.

El resultado seguiria necesitando extensiones custom para propuestas, evidencia y reglas del producto. Por eso, el reemplazo no se justifica con el alcance actual.

### Adaptador de compatibilidad futuro

Es considerablemente mas barato y preserva los boundaries:

1. Mantener `ChatRuntime`, servicios, repositorios, tools y auditoria sin cambios.
2. Traducir un input AG-UI validado a un comando de aplicacion de Umbral.
3. Proyectar `RuntimeEvent` a eventos AG-UI, con argumentos/resultados sensibles redactados.
4. Mantener reads de historial/sesion como endpoints de producto hasta que el protocolo resuelva sync/reattach de forma estable.
5. Ejecutar una suite de conformidad que cubra secuencia, desconexion, replay, interrupt/resume e idempotencia.

Este adaptador solo vale la pena cuando haya un consumidor real. Implementarlo preventivamente agregaria dos contratos que mantener.

## Recomendacion operativa

**Ahora:** no instalar `ag-ui-langgraph`, no reemplazar SSE ni adoptar CopilotKit. Documentar AG-UI como opcion de interoperabilidad, sin cambiar codigo.

**Reevaluar si ocurre al menos una de estas condiciones:**

- aparece un segundo cliente o canal que ya hable AG-UI;
- se decide usar generative UI o frontend tools de forma sistematica;
- mantener el parser/reducer propio genera bugs o costo recurrente medible;
- los paquetes core y LangGraph llegan a `1.x` o publican una politica clara de estabilidad;
- sync/reattach e interrupts convergen en un camino canonico compatible entre AG-UI y CopilotKit.

**Si se reevalua:** hacer un spike acotado de adaptador, no una migracion. Criterios de exito: 100% de los tests de chat actuales siguen pasando; ninguna tool nueva obtiene autoridad desde el cliente; ningun checkpoint se vuelve fuente de verdad; no se filtran argumentos/resultados sensibles; reconexion e idempotencia conservan sus invariantes; el segundo consumidor funciona sin extensiones privadas significativas.

## Conclusion

AG-UI es una buena apuesta de ecosistema y un protocolo sensato. **No es, todavia, una ventaja neta para el Umbral actual**, porque Umbral ya pago el costo de construir el borde y su valor diferencial vive en contratos de producto mas estrictos que el protocolo generico. La jugada con mejor relacion beneficio/riesgo es observar su estabilizacion y adoptarlo solo como adaptador de interoperabilidad cuando exista demanda real.
