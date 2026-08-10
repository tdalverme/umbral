# Feature Specification: Comportamiento conversacional y UI

**Feature Branch**: `011-conversational-ui`

**Created**: 2026-08-10

**Status**: Draft

**Input**: User description: "Arranquemos con la especificacion de la epica H4.3 - Comportamiento conversacional y UI del backlog, con alcance exacto UM-H4-017 a UM-H4-025."

## Clarifications

### Session 2026-08-10

- Q1 (alcance): La puerta de salida de H4 dice "el chat crea/refina busquedas", pero ningun item de H4.2/H4.3 cubre la creacion de una busqueda desde cero (las tools de H4.2 operan sobre un perfil existente). ¿Que pasa cuando el usuario quiere crear un radar desde el chat? → A: La creacion queda fuera de alcance: el alcance es exactamente UM-H4-017 a UM-H4-025 y no se amplia el backlog. Sin radar activo, la intencion se clasifica como fuera de alcance y el chat declara el limite y dirige al onboarding estructurado (H2.5). La creacion asistida desde el chat no se implementa en este incremento.
- Q2 (human-in-the-loop): Cuando el usuario "edita" una propuesta pendiente de cambio de perfil (UM-H4-019), ¿como se materializa la edicion sobre el objeto durable de H4.2, que es de un solo uso y debe conservar trazabilidad? → A: Nueva propuesta derivada: editar crea una propuesta nueva con el diff corregido y la original pasa a rechazada con motivo "editada por el usuario". La propuesta original nunca se muta (0 reescrituras), se conserva la trazabilidad completa y el un solo uso se mantiene en cada propuesta.
- Q3 (ubicacion del chat): ¿Donde vive el chat en la experiencia web: panel en la pagina del radar, vista dedicada o ambas? → A: Panel unico integrado en la pagina del radar: al abrirlo reanuda la ultima sesion del radar o crea una nueva, y permite empezar una conversacion nueva desde el mismo panel. 0 rutas dedicadas y 0 selector de sesiones en este incremento; las entradas contextuales en detalle y comparador llevan a este mismo panel.

## Operational Definitions

- **Intencion**: clasificacion versionada de la intencion de un mensaje del usuario dentro del conjunto permitido: consulta, refinamiento, comparacion, feedback y fuera de alcance. Es una decision auditada del graph run (con version de schema/prompt), nunca una ejecucion directa de texto sobre datos.
- **Acciones permitidas**: conjunto de efectos que la conversacion puede producir, todos derivados de tools explicitas de H4.2 y de la politica de confirmacion: leer perfil/matches/explicaciones, proponer y confirmar cambios, comparar, registrar feedback y consultar contexto urbano. 0 SQL libre, 0 ranking generativo y 0 mutaciones sin confirmacion.
- **Aclaracion de alto impacto**: interrupcion acotada de la conversacion cuando un parametro de alto impacto (presupuesto, zona, hard filter, radio) o una contradiccion con el perfil vigente no alcanza la confianza de la politica aprobada. Se formula como preguntas concretas y se integra al mismo turno; nunca adivina valores.
- **Human-in-the-loop**: flujo por el que toda propuesta de cambio de perfil se pausa en el checkpoint y espera una decision explicita del usuario (aprobar, editar o rechazar) antes de producir efectos; la ejecucion se reanuda desde el mismo checkpoint sin repetir acciones.
- **Propuesta (SearchProfileUpdateProposal)**: objeto durable y auditable de H4.2 con diff validado, impacto, estado y un solo uso; en H4.3 incorpora las transiciones interactivas de rechazo por el usuario y edicion, con motivo registrado.
- **Respuesta grounded**: respuesta del chat en la que el 100% de las afirmaciones sobre listings, criterios, razones o puntajes cita objetos persistentes y verificables (listing, criterio, evidence ref, score version, snapshot de perfil); cuando la evidencia falta o es debil, se declara y no se completan hechos.
- **Mini-card**: representacion persistente y navegable de un objeto de producto (listing) dentro del chat, con datos esenciales redactados y enlace al radar/detalle; el objeto nunca vive solo como texto en el hilo.
- **Eventos de ejecucion**: eventos tipados que el contrato de streaming entrega al cliente (fragmentos de respuesta, actividad de tools, interrupcion por confirmacion, mensaje completado, error y estado de ejecucion) para que la UI distinga cada estado sin ambiguedad.
- **Estado de ejecucion visible**: representacion explicita en la UI de lo que esta pasando con la maquina conversacional (enviando, ejecutando, esperando confirmacion, reanudando, fallo, completado) para que el usuario sepa que hacer en cada momento.
- **Entrada contextual**: punto de entrada al chat desde el detalle de un listing o el comparador, que conserva el search profile del radar de la sesion y acota el scope de evidencia al listing o a la comparacion.

## Review and Measurement Protocol

- La puerta de salida de H4.3 es que el usuario maneje y entienda su radar por lenguaje natural con intenciones compiladas a acciones permitidas, aclaraciones de alto impacto, human-in-the-loop, respuestas grounded y una UI conversacional accesible y persistente, antes de pasar a evals y operacion (H4.4).
- La compilacion de intencion se verifica confirmando que el 100% de los mensajes recibe una clasificacion registrada con version, que 0 texto se traduce directo en SQL/ranking/mutaciones y que las intenciones fuera de alcance se responden declarando el limite.
- Las aclaraciones se verifican probando que los parametros de alto impacto ambiguos o contradictorios con el perfil vigente siempre interrumpen con preguntas acotadas (0 adivinanzas) y que la politica de confianza queda registrada por turno.
- El human-in-the-loop se verifica probando aprobar/editar/rechazar sobre el mismo checkpoint: la reanudacion produce 0 repeticiones de efectos, las decisiones quedan auditadas en la propuesta y la espera vencida queda en estado tipado recuperable.
- El grounding se verifica confirmando que el 100% de las afirmaciones de producto del chat cita evidencia persistida navegable y que 0 afirmaciones se completan sin evidencia.
- Los contratos de streaming se verifican probando errores y permisos tipados (0 acceso cruzado), reenvio sin duplicados, historial paginado en orden y eventos distinguibles.
- La UI se verifica con tests de componente y de acceso de extremo a extremo sobre teclado, lectores de pantalla, streaming, retry, jump-to-latest, mini-cards y estados de reconexion; la suite de aislamiento y abuso de H4.2 sigue pasando sin regresiones.
- La persistencia se verifica confirmando que 0 oportunidades ni decisiones viven solo en el chat: todo listing citado es mini-card navegable y todo cambio propuesto es propuesta durable visible en la UI estructurada.
- Este incremento se integra al harness local (`scripts/check.ps1`) con la convencion de los incrementos previos, incluye la composicion de produccion diferida en H4.1 y cierra el flujo de extremo a extremo (API + web + workers).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Compilar intencion a acciones permitidas (Priority: P0)

Como usuario, quiero que Umbral entienda si quiero preguntar, refinar, comparar, dar feedback o algo fuera de su alcance, para que cada mensaje mio se traduzca en la accion correcta y nada mas.

**Why this priority**: Es la puerta de entrada del radar conversacional: una clasificacion incorrecta puede producir cambios no pedidos o afirmaciones sin respaldo; por eso la intencion se compila a acciones permitidas y nunca directo a datos.

**Independent Test**: El conjunto de prueba envia mensajes de consulta, refinamiento, comparacion, feedback, ambiguos y fuera de alcance, y verifica que la clasificacion registrada es la esperada y que 0 efectos no pedidos se producen.

**Acceptance Scenarios**:

1. **Given** un mensaje del usuario, **When** se procesa, **Then** se clasifica en exactamente una intencion del conjunto permitido (consulta, refinamiento, comparacion, feedback, fuera de alcance) y la clasificacion queda registrada en el graph run con su version de schema/prompt.
2. **Given** un mensaje de consulta sobre el perfil, matches o explicaciones, **When** se procesa, **Then** solo se usan las tools de lectura de H4.2: 0 mutaciones y 0 recomputaciones desde el chat.
3. **Given** un mensaje de refinamiento, **When** se procesa, **Then** se produce una propuesta de cambio (propose) y se espera confirmacion explicita; 0 cambios se aplican sin confirmacion.
4. **Given** un mensaje que pide puntajes, ordenamientos o cambios en lenguaje natural, **When** se procesa, **Then** 0 SQL libre y 0 ranking generativo: todo resultado proviene de codigo determinista (scoring, comparacion, tools).
5. **Given** un mensaje fuera de alcance (ajeno al radar o imposible), **When** se procesa, **Then** se declara el limite y se dirige a la alternativa estructurada (onboarding, detalle, comparador) cuando exista; 0 invenciones y 0 efectos.
6. **Given** un mensaje ambiguo entre dos intenciones, **When** se procesa, **Then** se deriva a aclaracion (UM-H4-018) en lugar de adivinar.

---

### User Story 2 - Aclaraciones de alto impacto (Priority: P0)

Como usuario, quiero que Umbral me pregunte antes de asumir valores de presupuesto, zona, hard filters o radio, para que ningun cambio de mi radar se apoye en suposiciones.

**Why this priority**: Cambiar criterios de alto impacto modifica el matching futuro; asumir valores o resolver contradicciones sin preguntar rompe la confianza y el principio de confirmacion de H4.2.

**Independent Test**: El conjunto de prueba envia pedidos con parametros de alto impacto ambiguos, incompletos o contradictorios con el perfil vigente y verifica que siempre se interrumpe con preguntas acotadas y 0 efectos.

**Acceptance Scenarios**:

1. **Given** un pedido con un parametro de alto impacto ambiguo (presupuesto sin numero, zona imprecisa, hard filter sin valor), **When** la confianza no supera la politica aprobada, **Then** se interrumpe la ejecucion y se formula una aclaracion concreta (parametro + formato u opciones) antes de crear propuesta alguna.
2. **Given** una contradiccion entre el pedido y el perfil vigente, **When** se detecta, **Then** la aclaracion la expone explicitamente para que el usuario decida; 0 cambios silenciosos.
3. **Given** la respuesta del usuario a la aclaracion, **When** se integra al mismo turno, **Then** se reevalua; si la ambiguedad persiste tras el maximo definido por politica, se declara que no puede aplicar el cambio y se sugiere la UI estructurada, sin inventar valores.
4. **Given** cualquier turno con parametros de alto impacto, **When** se decide aclarar o no, **Then** la decision y su confianza quedan registradas de forma auditable con la politica versionada.
5. **Given** una aclaracion, **When** el usuario responde, **Then** 0 propuestas se crean con parametros no confirmados y 0 cambios se aplican sin confirmacion (H4.2).

---

### User Story 3 - Human-in-the-loop: aprobar, editar o rechazar (Priority: P0)

Como usuario, quiero revisar cada cambio propuesto por el chat y aprobarlo, editarlo o rechazarlo antes de que toque mi radar, para que nada se aplique sin mi decision.

**Why this priority**: Es el guardrail central del producto: la confirmacion explicita de H4.2 se vuelve interactiva y reanudable, y toda decision queda auditada en la propuesta durable.

**Independent Test**: El conjunto de prueba interrumpe la ejecucion en la espera de confirmacion, ejecuta aprobar/editar/rechazar, reanuda el mismo checkpoint y verifica 0 repeticiones de efectos y estados auditados.

**Acceptance Scenarios**:

1. **Given** una propuesta de cambio presentada por el chat, **When** el usuario la aprueba, **Then** la propuesta se aplica con confirmacion e idempotency key (H4.2): perfil versionado, propuesta aprobada de un solo uso y recomputacion que preserva el run anterior.
2. **Given** una propuesta pendiente, **When** el usuario la rechaza interactivamente, **Then** la propuesta pasa a rechazada con el motivo registrado y auditable; 0 efectos en el perfil y 0 reaplicacion posible.
3. **Given** una propuesta pendiente, **When** el usuario pide editarla, **Then** se crea una propuesta nueva derivada con el diff corregido y la original pasa a rechazada con motivo "editada por el usuario"; la propuesta original no se muta (0 reescrituras), la trazabilidad queda completa y el un solo uso se mantiene en cada propuesta.
4. **Given** la ejecucion interrumpida por la espera de confirmacion, **When** el usuario decide, **Then** la ejecucion se reanuda desde el mismo checkpoint y 0 acciones ya aplicadas se repiten (0 duplicados).
5. **Given** una espera de confirmacion vencida (ventana definida por politica), **When** el usuario retoma, **Then** la ejecucion queda en estado tipado recuperable, la propuesta permanece pendiente segun politica y el usuario puede reanudarla o descartarla sin repetir acciones.
6. **Given** una propuesta pendiente creada desde el chat, **When** el usuario la retoma desde la UI estructurada del radar, **Then** ve y acciona el mismo objeto (banner de propuesta existente) sin divergencias entre vistas.

---

### User Story 4 - Respuestas grounded (Priority: P0)

Como usuario, quiero que cada afirmacion de Umbral sobre listings, criterios o razones este respaldada por evidencia que pueda revisar, para decidir sin dudar de lo que me dice.

**Why this priority**: Es donde se sostiene el principio de "0 afirmaciones sin evidencia interna" en la practica conversacional; la confianza de beta depende de que las citas sean verificables.

**Independent Test**: El conjunto de prueba revisa el 100% de las afirmaciones de producto de respuestas del chat y verifica que citan evidencia persistida navegable y que 0 hechos se completan sin evidencia.

**Acceptance Scenarios**:

1. **Given** una respuesta que menciona un listing, un criterio o una razon, **When** se presenta, **Then** cita el objeto persistente correspondiente (listing, criterio, evidence ref, score version, snapshot de perfil) y la cita es navegable.
2. **Given** evidencia faltante o debil (datos faltantes, run desactualizado, baja confianza), **When** se responde, **Then** se declara explicitamente y 0 hechos se completan.
3. **Given** una explicacion de un match, **When** se presenta, **Then** se basa en la explicacion persistida (H3.2) con score version, snapshot, criterios y evidence refs; 0 explicaciones inventadas en el chat.
4. **Given** una comparacion, **When** se presenta, **Then** se apoya en la comparacion estructurada persistida (H3.2) con dimensiones homogeneas, faltantes y tradeoffs; 0 ganador generativo.
5. **Given** una cita a un objeto, **When** el usuario la abre, **Then** llega al radar/detalle del objeto citado respetando el search scope de la sesion; 0 enlaces a objetos ajenos o fuera de vigencia.

---

### User Story 5 - Contratos de chat streaming (Priority: P0)

Como equipo, quiero contratos tipados y con errores claros para crear sesion, enviar mensaje, recibir eventos, reanudar y recuperar historial, para que la UI y el backend evolucionen sin romper la confianza de la conversacion.

**Why this priority**: Es la superficie de integracion del radar conversacional: errores tipados y permisos estrictos son la base de la UI y del aislamiento entre usuarios.

**Independent Test**: El conjunto de prueba ejercita cada operacion del contrato (crear, enviar, eventos, reanudar, historial) con usuarios autorizados, ids manipulados y reintentos, y verifica errores y permisos tipados con 0 duplicados.

**Acceptance Scenarios**:

1. **Given** un usuario autenticado, **When** crea una sesion de chat para su radar, **Then** la sesion queda ligada a su search profile y 0 datos de otros radares son accesibles, incluso con ids manipulados.
2. **Given** un mensaje enviado, **When** se procesa, **Then** la respuesta llega como eventos tipados (fragmentos, actividad de tools, interrupcion por confirmacion, completado, error, estado) y la UI puede distinguir cada estado.
3. **Given** una sesion con ejecucion en curso, **When** se envia otro mensaje a la misma sesion, **Then** se rechaza con estado tipado y recuperable (0 ejecuciones paralelas) y el cliente decide reintentar.
4. **Given** un envio fallido o desconectado, **When** el cliente reintenta con la misma clave, **Then** 0 mensajes duplicados y 0 efectos repetidos.
5. **Given** una sesion pausada o archivada, **When** se intenta enviar, **Then** se rechaza con error tipado y el historial sigue siendo recuperable.
6. **Given** una sesion con historial, **When** se recupera, **Then** se devuelve paginado y en orden con roles y contenido permitido, trazando a su graph run.
7. **Given** una operacion sin permiso o con ids ajenos, **When** se intenta, **Then** error tipado y 0 acceso cruzado.

---

### User Story 6 - Chat contextual accesible (Priority: P0)

Como usuario, quiero un chat ligado a mi radar que funcione por teclado y lectores de pantalla, con streaming, reintento y navegacion del historial, para poder usarlo sin friccion.

**Why this priority**: La UI conversacional es la cara del producto y la auditoria de accesibilidad de H6.3 la exigira; construirla accesible desde el inicio evita retrofits y exclusion de usuarios.

**Independent Test**: El conjunto de prueba opera el chat por teclado y con lectores de pantalla (roles, live regions, nombres, foco, contraste) en los flujos de streaming, retry y jump-to-latest, y verifica 0 acciones solo con mouse.

**Acceptance Scenarios**:

1. **Given** un radar activo, **When** el usuario abre el chat contextual, **Then** ve el panel unico del chat integrado en la pagina del radar con la conversacion de su radar y puede retomar donde la dejo; el panel reanuda la ultima sesion del radar o crea una nueva al abrirlo, y permite empezar una conversacion nueva desde el mismo panel sin salir de la pagina.
2. **Given** una respuesta en generacion, **When** el texto fluye, **Then** se muestra el streaming con indicacion de actividad y el estado del turno (enviando, ejecutando, esperando confirmacion, fallo, completado) sin ambiguedad.
3. **Given** un envio fallido, **When** el usuario reintenta, **Then** el mensaje no se duplica y el estado del hilo refleja el fallo y el reenvio.
4. **Given** una sesion con historial extenso, **When** el usuario la retoma, **Then** puede saltar a lo mas reciente (jump-to-latest) y navegar el historial paginado.
5. **Given** el chat, **When** se opera por teclado, **Then** envio con Enter, nueva linea con Shift+Enter, foco gestionado y navegacion/activacion de botones, mini-cards y enlaces; 0 acciones solo con mouse.
6. **Given** el chat, **When** se usa un lector de pantalla, **Then** roles, nombres accesibles y live regions anuncian generacion, estados y resultados; 0 contenido depende solo de color o animacion.
7. **Given** mensajes o listings con contenido arbitrario, **When** se renderizan, **Then** solo se muestra contenido permitido (H4.1): 0 HTML arbitrario, 0 media embebida y 0 scripts.

---

### User Story 7 - Acciones y mini-cards persistentes (Priority: P0)

Como usuario, quiero que cada listing que me muestre el chat sea una tarjeta que enlace a mi radar y que cada cambio propuesto muestre su diff con confirmacion, para que nada importante exista solo dentro de la conversacion.

**Why this priority**: Es la aplicacion del principio "el chat no es la unica fuente de verdad": las oportunidades y decisiones viven como objetos persistentes y la UI estructurada las refleja.

**Independent Test**: El conjunto de prueba recorre respuestas con listings y cambios propuestos y verifica que el 100% se renderiza como mini-cards navegables y diffs accionables persistidos.

**Acceptance Scenarios**:

1. **Given** una respuesta que cita listings, **When** se renderiza, **Then** cada listing es una mini-card persistente con datos esenciales redactados y enlace al radar/detalle del objeto; 0 listings que existen solo como texto en el chat.
2. **Given** un cambio de perfil propuesto, **When** se presenta, **Then** muestra el diff y su impacto con acciones de confirmacion y deshacer; la decision persiste en la propuesta durable, no solo en el hilo.
3. **Given** una propuesta pendiente creada desde el chat, **When** se revisa la UI estructurada del radar, **Then** aparece el mismo objeto (estado, diff, acciones) sin divergencias con el chat.
4. **Given** feedback registrado desde el chat, **When** se revisa el detalle del listing, **Then** el evento de feedback persistido (H3.3/H4.2) se refleja en la UI estructurada.
5. **Given** cualquier accion del chat (propuesta, feedback, comparacion), **When** se ejecuta, **Then** queda registrada como evento auditable y visible en las vistas de producto correspondientes.

---

### User Story 8 - Reconexion, interrupcion y error parcial (Priority: P0)

Como usuario, quiero entender siempre que esta pasando con mi conversacion cuando se corta, se interrumpe o falla, para poder retomar sin confundirme ni duplicar mensajes.

**Why this priority**: La reanudacion confiable es la promesa del runtime (H4.1); la UI debe traducir esos estados a lenguaje humano para que el usuario sepa que hacer.

**Independent Test**: El conjunto de prueba interrumpe la ejecucion en distintos puntos (durante generacion, en espera de confirmacion, por fallo) y verifica estados claros, reanudacion sin duplicados y 0 fragmentos parciales como respuesta final.

**Acceptance Scenarios**:

1. **Given** una desconexion durante la generacion, **When** se detecta, **Then** la UI muestra el estado de interrupcion y ofrece reanudar desde el ultimo checkpoint; 0 fragmentos parciales se presentan como respuesta final (solo respuestas completas persisten, H4.1).
2. **Given** una interrupcion por espera de confirmacion, **When** el usuario vuelve, **Then** la UI distingue "esperando confirmacion" de otros estados y ofrece aprobar/editar/rechazar sin repetir acciones.
3. **Given** un fallo de red o de servicio, **When** ocurre, **Then** el mensaje en el hilo refleja el fallo y permite reintentar sin duplicar el mensaje ni los efectos.
4. **Given** una sesion con ejecucion en curso en otra pestana o instancia, **When** el usuario intenta enviar, **Then** la UI muestra el estado tipado y le permite seguir la misma ejecucion o esperar; 0 ejecuciones paralelas.
5. **Given** cualquier estado del graph (espera, reanudando, fallo, en curso), **When** se muestra, **Then** es distinguible y accionable para el usuario, sin mensajes duplicados.

---

### User Story 9 - Entrada contextual en detalle/comparador (Priority: P1)

Como usuario, quiero preguntar sobre un listing concreto o sobre una comparacion desde su contexto, para que las respuestas conserven mi radar y la evidencia del objeto que estoy mirando.

**Why this priority**: Conecta el chat con las vistas de decision del producto y conserva el scope correcto de evidencia; es P1 porque agrega valor sin ser bloqueante del flujo principal.

**Independent Test**: El conjunto de prueba lanza preguntas desde detalle y comparador y verifica que el search profile y el scope de evidencia se conservan y las citas retornan al contexto correcto.

**Acceptance Scenarios**:

1. **Given** el detalle de un listing, **When** el usuario pregunta sobre el, **Then** la pregunta se procesa en la sesion del radar con el scope de evidencia acotado al listing; 0 datos de otros radares.
2. **Given** el comparador, **When** el usuario pregunta sobre la comparacion, **Then** la respuesta usa la comparacion estructurada persistida (H3.2) con el mismo conjunto comparado.
3. **Given** una respuesta contextual, **When** cita evidencia, **Then** los enlaces retornan al contexto correcto (detalle o comparador) respetando permisos y redaccion (H4.2).
4. **Given** un radar sin sesion de chat, **When** el usuario pregunta desde detalle, **Then** se crea o reutiliza la sesion del radar sin perder el contexto del listing.

### Edge Cases

- Mensaje con varias intenciones mezcladas: se clasifica con la intencion dominante y se aclara lo ambiguo antes de actuar; 0 efectos parciales.
- Parametro de alto impacto ausente, incompleto o fuera de rango: aclaracion acotada; 0 adivinanzas y 0 propuestas con valores no confirmados.
- Contradiccion entre el pedido y el perfil vigente: la aclaracion la expone; 0 cambios silenciosos.
- Ambiguedad persistente tras el maximo de aclaraciones: se declara la imposibilidad y se sugiere la UI estructurada.
- Intencion fuera de alcance (temas ajenos al radar, acciones no soportadas): respuesta que declara el limite y dirige a la alternativa estructurada cuando existe.
- Pedido de crear un radar desde el chat sin radar activo: fuera de alcance; el chat declara el limite y dirige al onboarding estructurado (H2.5); 0 flujos de creacion en el chat.
- Propuesta rechazada interactivamente: transicion a rechazada con motivo, 0 efectos y 0 reaplicacion posible.
- Propuesta editada: se crea una propuesta nueva derivada con el diff corregido y la original pasa a rechazada con motivo "editada por el usuario"; 0 reescrituras del objeto original y trazabilidad completa.
- Propuesta vencida durante la espera: estado tipado recuperable; la propuesta permanece pendiente segun politica y el usuario puede reanudarla o descartarla.
- Ejecucion en curso en otra pestana: estado tipado, 0 ejecuciones paralelas y el usuario puede seguir la misma ejecucion.
- Desconexion durante la generacion: reanudacion desde el ultimo checkpoint, 0 fragmentos parciales como respuesta final y 0 mensajes duplicados.
- Error parcial o fallo de red: reintento idempotente, 0 duplicados y estado del mensaje sin ambiguedad.
- Sesion pausada o archivada: no acepta mensajes nuevos, historial recuperable (H4.1).
- Contenido arbitrario en mensajes o listings: solo contenido permitido se renderiza; 0 HTML arbitrario, media o scripts (H4.1).
- Cita a objeto fuera del search scope o ya no vigente: se declara la falta de evidencia y 0 enlaces a objetos ajenos.
- Historial extenso: paginacion y jump-to-latest sin perdida de orden.
- 0 accesos cruzados con ids manipulados en contratos y citas: denegados con error tipado en el 100% de los casos.

## Requirements *(mandatory)*

### Functional Requirements

#### Compilacion de intencion (UM-H4-017)

- **FR-001**: El agente MUST clasificar cada mensaje del usuario en exactamente una intencion del conjunto permitido —consulta, refinamiento, comparacion, feedback y fuera de alcance— y la clasificacion MUST quedar registrada en el graph run con la version del schema/prompt que la produjo.
- **FR-002**: La clasificacion MUST NO traducir texto directamente en SQL, ranking ni mutaciones: toda accion posterior MUST derivar de las tools permitidas de H4.2 y de la politica de confirmacion. 0 SQL libre, 0 ranking generativo y 0 recomputaciones desde el chat.
- **FR-003**: Un mensaje ambiguo entre intenciones o con parametros de alto impacto no confirmados MUST derivar en aclaracion (UM-H4-018) con 0 efectos.
- **FR-004**: Una intencion fuera de alcance MUST responderse declarando el limite y dirigiendo a la alternativa estructurada (onboarding, detalle, comparador) cuando exista; 0 invenciones y 0 efectos.
- **FR-005**: La creacion de una busqueda/radar desde cero desde el chat MUST quedar fuera de alcance: sin radar activo, la intencion de crear MUST clasificarse como fuera de alcance y el chat MUST declarar el limite y dirigir al onboarding estructurado (H2.5); 0 flujos de creacion nuevos se implementan en el chat.

#### Aclaraciones de alto impacto (UM-H4-018)

- **FR-006**: Cuando un parametro de alto impacto (presupuesto, zona, hard filter, radio) o una contradiccion con el perfil vigente no alcance la confianza de la politica aprobada, el agente MUST interrumpir la ejecucion y formular una aclaracion concreta (parametro + formato u opciones) antes de crear propuesta alguna; 0 adivinanzas.
- **FR-007**: Las aclaraciones MUST presentarse en lenguaje claro, acotadas a un maximo de preguntas por turno definido por politica y sin exponer datos de otros radares.
- **FR-008**: La respuesta del usuario a la aclaracion MUST integrarse al mismo turno y reevaluarse; si la ambiguedad persiste tras el maximo definido por politica, el agente MUST declarar que no puede aplicar el cambio y sugerir la UI estructurada, sin inventar valores.
- **FR-009**: La politica de confianza y sus umbrales MUST ser versionados, y cada decision de aclarar o no MUST quedar registrada con su confianza por turno (auditable).
- **FR-010**: La aclaracion MUST ser previa a la propuesta: 0 propuestas con parametros no confirmados y 0 cambios sin confirmacion explicita (H4.2).

#### Human-in-the-loop (UM-H4-019)

- **FR-011**: Toda propuesta de cambio de perfil del chat MUST presentarse con diff e impacto y esperar la decision explicita del usuario sobre el mismo checkpoint; reanudar tras la decision MUST NO repetir acciones ya aplicadas (0 duplicados).
- **FR-012**: Aprobar MUST aplicar la propuesta con confirmacion e idempotency key (H4.2): perfil versionado, propuesta aprobada de un solo uso y recomputacion que preserva el run anterior; la UI MUST reflejar la propuesta aprobada.
- **FR-013**: Rechazar interactivamente MUST transicionar la propuesta pendiente a rechazada con el motivo del usuario registrado y auditable; 0 efectos en el perfil y 0 reaplicacion posible.
- **FR-014**: Editar una propuesta pendiente MUST crear una propuesta nueva derivada con el diff corregido y MUST transicionar la original a rechazada con motivo "editada por el usuario"; la propuesta original MUST NO mutarse (0 reescrituras), la trazabilidad MUST quedar completa y el un solo uso MUST mantenerse en cada propuesta.
- **FR-015**: La espera por confirmacion MUST tener una ventana definida por politica: al vencer, la ejecucion MUST quedar en estado tipado recuperable, la propuesta MUST permanecer pendiente segun politica, y el usuario MUST poder reanudarla o descartarla sin repetir acciones.
- **FR-016**: El chat MUST NO bloquear la sesion durante la espera: la propuesta pendiente MUST ser visible y accionable desde la UI estructurada del radar (banner de propuesta existente) y desde el chat, con el mismo estado y 0 divergencias.

#### Respuestas grounded (UM-H4-020)

- **FR-017**: El 100% de las afirmaciones del chat sobre listings, criterios, razones o puntajes MUST citar objetos persistentes y verificables (listing, criterio, evidence ref, score version, snapshot de perfil); 0 afirmaciones sin evidencia interna.
- **FR-018**: Cuando la evidencia falte o sea debil (datos faltantes, run desactualizado, baja confianza), el chat MUST declararlo explicitamente y MUST NO completar hechos.
- **FR-019**: Toda cita a un listing MUST ser navegable: enlaza al radar/detalle del objeto citado respetando el search scope de la sesion; 0 enlaces a objetos ajenos o fuera de vigencia.
- **FR-020**: El contenido de las respuestas MUST construirse sobre salidas redactadas de tools (H4.2) y explicaciones/comparaciones persistidas (H3.2); 0 texto generado que reemplace o invente scores, criterios o evidencia.

#### Contratos de chat streaming (UM-H4-021)

- **FR-021**: El sistema MUST exponer contratos tipados y versionados para crear sesion, enviar mensaje, recibir eventos de ejecucion, reanudar ejecucion y recuperar historial paginado en orden; cada operacion MUST validar el permiso sobre la sesion (usuario autenticado y search profile del radar de la sesion), con 0 acceso cruzado incluso con ids manipulados.
- **FR-022**: El 100% de las operaciones MUST devolver errores tipados y accionables (ejecucion en curso, sesion pausada/archivada, permiso denegado, mensaje fuera de limites de contenido permitido, sesion inexistente); 0 errores opacos.
- **FR-023**: Los eventos de ejecucion MUST ser tipados y distinguibles: fragmentos de respuesta, actividad de tools, interrupcion por confirmacion, mensaje completado, error y estado de ejecucion.
- **FR-024**: El envio de mensajes MUST ser reenviable sin duplicar: reintentar con la misma clave MUST producir 0 mensajes duplicados y 0 efectos repetidos.
- **FR-025**: El contrato MUST declarar sus limites (longitud de mensaje, volumen de eventos, expiracion de la conexion) y el cliente tipado de la web MUST regenerarse y verificarse con la convencion del proyecto.

#### Chat contextual accesible (UM-H4-022)

- **FR-026**: El chat MUST estar contextualmente ligado al radar de la sesion (search profile) y MUST integrarse como panel unico en la pagina del radar: al abrirlo MUST reanudar la ultima sesion del radar o crear una nueva, y MUST permitir empezar una conversacion nueva desde el mismo panel; 0 rutas dedicadas y 0 selector de sesiones en este incremento. El panel MUST mostrar el streaming de la respuesta con indicacion de actividad y distinguir los estados del turno (enviando, ejecutando, esperando confirmacion, fallo, completado) sin ambiguedad.
- **FR-027**: El chat MUST soportar reintento de un envio fallido sin duplicar mensajes y jump-to-latest al retomar una sesion con historial paginado.
- **FR-028**: El chat MUST operarse completo por teclado: envio con Enter, nueva linea con Shift+Enter, foco gestionado y navegacion/activacion de botones, mini-cards y enlaces; 0 acciones solo con mouse.
- **FR-029**: El chat MUST ser operable con lectores de pantalla: roles, nombres accesibles y live regions para generacion, estados y resultados; 0 contenido que dependa solo de color o animacion.
- **FR-030**: El chat MUST renderizar solo contenido permitido (H4.1): 0 HTML arbitrario, 0 media embebida y 0 scripts desde mensajes o listings.

#### Acciones y mini-cards persistentes (UM-H4-023)

- **FR-031**: Toda referencia del chat a un listing MUST renderizarse como mini-card persistente y navegable con datos esenciales redactados y enlace al radar/detalle; 0 listings que existen solo como texto en el chat (principio I).
- **FR-032**: Todo cambio de perfil del chat MUST mostrar su diff e impacto con confirmacion y deshacer, y la decision MUST persistir en la propuesta durable; 0 decisiones que viven solo en el hilo.
- **FR-033**: Las propuestas pendientes creadas desde el chat MUST ser visibles y accionables desde la UI estructurada del radar y desde el chat, con el mismo estado y 0 divergencias entre vistas.
- **FR-034**: Las acciones del chat (feedback, propuestas, comparaciones) MUST reflejarse en los objetos de producto existentes y sus vistas (feedback en detalle, propuestas en el radar); 0 acciones solo en el hilo.

#### Reconexion, interrupcion y error parcial (UM-H4-024)

- **FR-035**: La UI MUST distinguir explicitamente los estados del graph (esperando confirmacion, reanudando, fallo, ejecucion en curso) y mostrar al usuario que hacer en cada uno, sin mensajes duplicados.
- **FR-036**: Ante una desconexion durante la generacion, la UI MUST detectarla y ofrecer reanudar la ejecucion desde el ultimo checkpoint; 0 fragmentos parciales se presentan como respuesta final (solo respuestas completas persisten, H4.1).
- **FR-037**: Ante un error parcial o de red, el reintento MUST NO duplicar mensajes ni efectos (idempotencia del contrato) y el estado del mensaje en el hilo MUST reflejar fallo/reenvio sin ambiguedad.
- **FR-038**: Con una ejecucion en curso en otra pestana o instancia, la UI MUST mostrar el estado tipado y permitir seguir la misma ejecucion o esperar; 0 ejecuciones paralelas sobre la misma sesion.

#### Entrada contextual en detalle/comparador (UM-H4-025, P1)

- **FR-039**: Desde el detalle de un listing y desde el comparador, el usuario MUST poder hacer preguntas contextuales que conservan el search profile del radar de la sesion y acotan el scope de evidencia al listing o a la comparacion.
- **FR-040**: Las respuestas contextuales MUST citar la evidencia persistida del contexto (explicacion y comparacion estructurada, H3.2) y sus enlaces MUST retornar al contexto correcto (detalle o comparador), respetando permisos y redaccion (H4.2).

#### Transversal

- **FR-041**: El incremento MUST integrar su harness de verificacion en `scripts/check.ps1` con la convencion de los incrementos previos, cubriendo contratos, agente y web (tests de componente, contract y acceso), sin regresiones en la suite de aislamiento y abuso de H4.2.
- **FR-042**: El incremento MUST cerrar el follow-up diferido de H4.1: la composicion de produccion del runtime sirve el chat de extremo a extremo (API, web y workers) y se verifica en el harness local.
- **FR-043**: La UI del chat MUST medir y exponer metricas de latencia percibida (primer fragmento) y errores de streaming que alimenten los budgets de performance de UM-H6-017.

### Key Entities

- **Intent**: clasificacion versionada de la intencion de un mensaje (consulta, refinamiento, comparacion, feedback, fuera de alcance), registrada en el graph run con la version de schema/prompt; 0 efectos directos desde texto.
- **SearchProfileUpdateProposal**: objeto durable y auditable de H4.2 (diff, impacto, estado, un solo uso, vigencia, version base del perfil) extendido en H4.3 con transiciones interactivas: rechazo por el usuario con motivo y edicion segun la politica aprobada; conserva trazabilidad completa.
- **PendingAction**: accion propuesta sin confirmar en el estado de la sesion (H4.1) que el flujo aprobar/editar/rechazar consume sobre el mismo checkpoint.
- **ChatMessage / ChatSession**: objetos persistentes de H4.1 (roles, contenido permitido, estado, lineage a graph runs) que el contrato de streaming crea, pagina y reanuda; 0 mensajes parciales persistidos.
- **ChatEvent**: evento tipado del contrato de streaming (fragmento, actividad de tool, interrupt, completado, error, estado) que la UI consume para distinguir estados.
- **MiniCard**: referencia tipada a un objeto de producto (listing) dentro del mensaje (contenido permitido H4.1) con datos esenciales redactados y enlace navegable al radar/detalle.
- **ToolRun / GraphRun**: registros de H4.1/H4.2 donde quedan la clasificacion de intencion, las aclaraciones, las decisiones HITL y las citas, con versiones y correlacion.
- **Explanation / EvidenceRef / StructuredComparison**: objetos persistidos (H3.2) que las respuestas grounded citan; 0 explicaciones generadas en el chat.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Compilar intencion | UM-H4-017 |
| User Story 2 - Aclaraciones de alto impacto | UM-H4-018 |
| User Story 3 - Human-in-the-loop | UM-H4-019 |
| User Story 4 - Respuestas grounded | UM-H4-020 |
| User Story 5 - Contratos de chat streaming | UM-H4-021 |
| User Story 6 - Chat contextual accesible | UM-H4-022 |
| User Story 7 - Acciones y mini-cards persistentes | UM-H4-023 |
| User Story 8 - Reconexion, interrupcion y error parcial | UM-H4-024 |
| User Story 9 - Entrada contextual en detalle/comparador | UM-H4-025 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H4-017 | FR-001, FR-002, FR-003, FR-004, FR-005 | US1.1-US1.6, SC-001 |
| UM-H4-018 | FR-006, FR-007, FR-008, FR-009, FR-010 | US2.1-US2.5, SC-002 |
| UM-H4-019 | FR-011, FR-012, FR-013, FR-014, FR-015, FR-016 | US3.1-US3.6, SC-003 |
| UM-H4-020 | FR-017, FR-018, FR-019, FR-020 | US4.1-US4.5, SC-004 |
| UM-H4-021 | FR-021, FR-022, FR-023, FR-024, FR-025 | US5.1-US5.7, SC-005 |
| UM-H4-022 | FR-026, FR-027, FR-028, FR-029, FR-030 | US6.1-US6.7, SC-006 |
| UM-H4-023 | FR-031, FR-032, FR-033, FR-034 | US7.1-US7.5, SC-007 |
| UM-H4-024 | FR-035, FR-036, FR-037, FR-038 | US8.1-US8.5, SC-008 |
| UM-H4-025 | FR-039, FR-040 | US9.1-US9.4, SC-009 |
| Transversal (todos) | FR-041, FR-042, FR-043 | SC-010 |

## Constitution Alignment *(mandatory)*

- **Persistent radar as product truth**: el chat renderiza listings como mini-cards navegables y las decisiones (aprobar/editar/rechazar) persisten en propuestas durables visibles en la UI estructurada; 0 oportunidades ni decisiones viven solo en el chat. Sustenta el principio I.
- **Auditable deterministic matching**: la intencion se compila a acciones permitidas, 0 texto a SQL/ranking, y las respuestas citan evidencia persistida (H3.2/H4.2); el chat nunca produce scores ni ganadores generativos. Sustenta el principio II.
- **Layered dependency direction**: la UI consume contratos tipados sobre la capa de aplicacion y el agente; 0 acceso libre a la base y el chat opera solo via tools permitidas (H4.2). Sustenta el principio III.
- **Minimal verifiable change**: el incremento se limita a UM-H4-017 a UM-H4-025 (mas el cierre del follow-up de composicion de produccion diferido de H4.1); 0 cambios a matching/scoring y 0 features especulativas; toda verificacion por harness y tests. Sustenta el principio IV.
- **Data lineage, observability and trust**: clasificaciones, aclaraciones, decisiones HITL y citas quedan registradas con versiones y correlacion en graph/tool runs; la incertidumbre se declara honestamente. Sustenta el principio V.
- **Versioned prompts, models and schemas**: la clasificacion de intencion, la politica de confianza y el contrato de streaming son versionados y auditables; las respuestas citan score version y snapshots. Sustenta los principios II y V.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los mensajes recibe una clasificacion de intencion registrada con version en el conjunto permitido; 0 texto convertido directo en SQL, ranking o mutaciones y 0 efectos para intenciones fuera de alcance.
- **SC-002**: El 100% de los turnos con parametros de alto impacto ambiguos o contradictorios con el perfil vigente produce una aclaracion acotada antes de cualquier propuesta; 0 adivinanzas, 0 propuestas con parametros no confirmados y las decisiones de aclarar quedan auditadas.
- **SC-003**: El 100% de los cambios de perfil del chat pasa por aprobar/editar/rechazar sobre el mismo checkpoint con 0 repeticiones de efectos; el 100% de las decisiones queda auditada en la propuesta (motivo, estado) y la espera vencida queda en estado tipado recuperable.
- **SC-004**: El 100% de las afirmaciones de producto del chat cita evidencia persistida navegable; 0 afirmaciones sin respaldo y 0 hechos completados ante evidencia faltante o debil.
- **SC-005**: El 100% de las operaciones del contrato de streaming devuelve errores y permisos tipados; 0 acceso cruzado con ids manipulados y 0 mensajes duplicados al reintentar.
- **SC-006**: El chat opera completo por teclado y con lectores de pantalla (roles, live regions, nombres, foco, contraste) y soporta streaming, retry y jump-to-latest; la auditoria automatizada y manual no encuentra bloqueantes.
- **SC-007**: El 100% de los listings citados se renderiza como mini-card navegable al radar/detalle y el 100% de los cambios propuestos muestra diff con confirmacion; 0 objetos de producto que viven solo en el chat y 0 divergencias entre chat y UI estructurada.
- **SC-008**: En el 100% de las desconexiones, interrupciones y errores parciales el usuario distingue el estado (espera, reanudando, fallo, en curso) y reanuda sin mensajes duplicados ni fragmentos parciales como respuesta final.
- **SC-009**: El 100% de las preguntas desde detalle/comparador conserva el search profile y el scope de evidencia del contexto y sus citas retornan al contexto correcto.
- **SC-010**: El harness del incremento corre en `scripts/check.ps1` con la composicion de produccion de extremo a extremo (API + web + workers) y sin regresiones en la suite de aislamiento y abuso de H4.2; la UI mide y expone primer fragmento y errores de streaming.

## Assumptions

- El alcance incluye exactamente UM-H4-017 a UM-H4-025 (Epica H4.3 - Comportamiento conversacional y UI), mas el cierre del follow-up diferido de H4.1: la composicion de produccion del runtime para servir el chat. Los evals, costos y operacion (H4.4) y la proactividad (H5) quedan fuera y se especifican en sus propios incrementos.
- Depende de la maquinaria existente y NO la reimplementa: runtime con sesiones, mensajes, checkpoints, contenido permitido y streaming reanudable (H4.1); tools explicitas con contrato comun y propuestas durables (H4.2); explicaciones, evidencia y comparacion estructurada (H3.2); feedback y propuestas de aprendizaje (H3.3); perfiles y radares persistentes (H2.3).
- La compilacion de intencion es una decision del graph run con version de schema/prompt y 0 efectos directos desde texto; las acciones derivan de las tools de H4.2.
- La politica de confianza de aclaraciones y sus umbrales, el maximo de preguntas por turno y la ventana de espera de confirmacion son parametros de politica versionados; los valores concretos se definen en el plan, no en el spec.
- [RESUELTO Q1 - opcion A]: la creacion de una busqueda/radar desde cero desde el chat queda fuera de alcance: ningun item de H4.2/H4.3 la cubre (las tools operan sobre un perfil existente) y no se amplia el backlog; sin radar activo, el chat declara el limite y dirige al onboarding estructurado (H2.5).
- [RESUELTO Q2 - opcion A]: la edicion de propuestas se materializa como nueva propuesta derivada: la original pasa a rechazada con motivo "editada por el usuario", nunca se muta (0 reescrituras) y la trazabilidad y el un solo uso se conservan en cada propuesta.
- UM-H4-025 es P1 y se incluye en el incremento, consistente con la convencion de incrementos previos que incluyeron items P1 de su epica; su verificacion es parte del harness.
- El chat vive en la web existente como panel unico integrado en la pagina del radar, contextualmente ligado al search profile de la sesion: al abrirlo reanuda la ultima sesion del radar o crea una nueva, y permite empezar una conversacion nueva desde el mismo panel; 0 rutas dedicadas y 0 selector de sesiones (decision de clarificacion Q3). Las entradas contextuales en detalle y comparador reutilizan la sesion del radar con scope de evidencia acotado (UM-H4-025).
- El idioma de copy, casos y registros es espanol (CABA), sobre el dataset controlado.
- La UI mide latencia percibida (primer fragmento) y errores de streaming para alimentar UM-H6-017; los budgets de performance se fijan en H6.3, no en este incremento.
- 0 cambios a matching, scoring, dedupe o ingesta: el incremento agrega comportamiento conversacional, contratos y UI sobre objetos persistentes existentes.
