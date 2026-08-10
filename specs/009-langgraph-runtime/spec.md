# Feature Specification: Runtime LangGraph

**Feature Branch**: `009-langgraph-runtime`

**Created**: 2026-08-09

**Status**: Draft

**Input**: User description: "Arranquemos con la especificacion de la epica H4.1 - Runtime LangGraph del backlog, con alcance exacto UM-H4-001 a UM-H4-006."

## Clarifications

### Session 2026-08-09

- Q: ¿Que politica de retencion aplica a los datos conversacionales de la beta
  (sesiones, mensajes y checkpoints)? → A: Sesiones y mensajes persisten
  mientras exista la cuenta del usuario y se borran con ella (alineado con
  UM-H6-011); los checkpoints son estado operativo con ventana corta de
  inactividad (default 30 dias, parametrizable) y se purgan sin tocar el
  historial persistido. La politica queda documentada, versionada y con
  migracion compatible.
- Q: Cuando una sesion ya tiene una ejecucion en curso, ¿que hace el sistema
  con una segunda solicitud a la misma sesion? → A: Se rechaza con un estado
  tipado y recuperable ("ejecucion en curso") y 0 ejecuciones paralelas; el
  cliente decide si reintenta. No se encola ni se ignoran duplicados.
- Q: ¿Que hace que una sesion pase de activa a pausada o archivada sin UI en
  H4.1? → A: La sesion refleja el estado de su search profile: si el radar se
  pausa o archiva (H2.3), la sesion pasa a pausada/archivada y no acepta
  mensajes nuevos; el historial sigue siendo recuperable.
- Q: Si una ejecucion se interrumpe a mitad de la generacion, ¿que se persiste
  como mensaje del asistente? → A: Solo respuestas completas: los fragmentos
  intermedios viven en el checkpoint y la reanudacion completa el mensaje;
  0 mensajes parciales se persisten en el historial.

## Operational Definitions

- **Sesion de chat**: conversacion persistente que vincula un usuario con un
  search profile y agrupa mensajes y ejecuciones. Es un objeto de producto
  durable, no un estado transitorio; el usuario puede retomarla entre
  requests.
- **Mensaje**: unidad minima de una conversacion, persistida con rol, contenido
  tipado permitido, estado y lineage a la ejecucion que lo produjo. Una vez
  creado es inmutable y no puede reescribirse.
- **Checkpoint**: estado serializado de una ejecucion en un punto dado (mensajes
  del turno, contexto, intencion, pending action, tool results y errores) que
  permite reanudar tras una interrupcion. Es estado operativo y NUNCA fuente de
  verdad de producto: no reemplaza busquedas, listings, recomendaciones,
  feedback ni eventos de auditoria.
- **Graph run**: ejecucion de la maquina de conversacion para una sesion:
  registra version del schema/topologia, estado (pendiente, ejecutando,
  completado, fallido, interrumpido), latencia, errores resumidos, uso y
  correlacion, sin copiar PII innecesaria.
- **Node/tool run**: ejecucion de un nodo o tool dentro de un graph run con su
  propio estado, latencia, errores y uso; queda vinculada al mismo id de
  correlacion.
- **Adapter de modelo**: punto unico por el que la maquina de conversacion
  habla con un modelo de lenguaje, con salidas estructuradas, timeout, reintento
  acotado, registro de uso y versiones de modelo/prompt/schema. El dominio no
  conoce proveedores concretos.
- **Contenido permitido**: tipos de contenido que un mensaje puede almacenar
  (texto, referencias tipadas a objetos de producto, tool calls/resultados),
  con limites de longitud y sin HTML arbitrario ni media.
- **Pending action**: accion propuesta por la conversacion (por ejemplo, un
  cambio de perfil) que aun no fue confirmada; se modela en el estado v1 y su
  flujo de aprobacion/edicion/rechazo se consume en el incremento H4.3.

## Review and Measurement Protocol

- La puerta de salida de H4.1 es que la maquina de conversacion funcione de
  forma persistente, reanudable, aislada por usuario/sesion y auditable antes
  de agregar tools (H4.2), comportamiento conversacional y UI (H4.3) o evals
  (H4.4).
- Las sesiones y mensajes se verifican confirmando que quedan persistidos como
  objetos de producto vinculados a usuario y search profile, con roles y
  contenido permitido, y que el historial es recuperable en orden.
- El estado de ejecucion se verifica confirmando que todo valor checkpointed es
  serializable, que el schema esta versionado y que un cambio de schema migra
  sin perder capacidad de reanudar.
- El aislamiento se verifica probando que un usuario nunca reanuda o lee
  sesiones de otro, ni siquiera con ids manipulados.
- La reanudacion se verifica interrumpiendo una ejecucion (desconexion, fallo
  de red o de modelo) y confirmando que se retoma desde el ultimo checkpoint y
  que los efectos ya aplicados NO se repiten (0 duplicados).
- El adapter de modelo se verifica con salidas estructuradas: el 100% de las
  respuestas respeta los esquemas permitidos, las invalidas se rechazan o
  reintentan de forma acotada, y el timeout/reintentos se comportan segun la
  politica sin exponer proveedores al dominio.
- Los graph runs y node/tool runs se verifican confirmando que el 100% de las
  ejecuciones registra version, estado, latencia, errores, uso y correlacion,
  y que 0 datos de PII innecesaria se copian a registros o logs.
- La retencion y la politica de limpieza se verifican segun la decision de la
  sesion de clarificacion: sesiones y mensajes se conservan mientras exista la
  cuenta y se borran con ella; los checkpoints con ventana corta de inactividad
  se purgan sin alterar el historial; la politica es documentada, versionada y
  con migracion compatible.
- Este incremento se integra al harness local (`scripts/check.ps1`) de acuerdo
  con la convencion de los incrementos previos y no expone superficies nuevas
  de usuario ni contratos HTTP (los contratos de chat son de H4.3).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Conversacion persistente ligada al radar (Priority: P0)

Como usuario de beta, quiero que mi conversacion con Umbral quede ligada a mi
radar y persista entre visitas, para poder retomar una conversacion donde la
deje sin perder contexto.

**Why this priority**: Es la base del radar conversacional: sin sesiones y
mensajes persistentes como objetos de producto, el chat seria un estado
efimero que viola el principio de que las decisiones viven en objetos
durables, no solo en la conversacion.

**Independent Test**: El conjunto de prueba crea una sesion, envia mensajes,
cierra la ejecucion y verifica que la sesion y sus mensajes quedan persistidos
y recuperables.

**Acceptance Scenarios**:

1. **Given** un usuario autenticado con un search profile, **When** se crea una
   sesion de chat, **Then** la sesion queda vinculada a ese usuario y a ese
   search profile y persiste entre requests.
2. **Given** una conversacion con varios turnos, **When** se recupera el
   historial, **Then** los mensajes se devuelven en orden con su rol, contenido
   permitido y estado, y cada mensaje traza a la ejecucion que lo produjo.
3. **Given** un mensaje creado, **When** se intenta modificar, **Then** es
   inmutable: 0 mensajes se reescriben y todo cambio de estado genera un evento
   de auditoria.
4. **Given** una sesion sin actividad, **When** se consulta su estado, **Then**
   el estado refleja el de su search profile (activa, pausada o archivada) sin
   ambiguedad, y una sesion pausada o archivada no acepta mensajes nuevos pero
   conserva el historial recuperable.

---

### User Story 2 - Ejecucion reanudable sin efectos duplicados (Priority: P0)

Como usuario, quiero que si mi conexion se corta o el sistema falla a mitad de
una respuesta, la conversacion pueda reanudarse desde donde quedo sin que se
repitan acciones ya realizadas.

**Why this priority**: Define el contrato de confianza del runtime: la
reanudacion tras interrupcion es una promesa de no duplicar efectos, y el
estado versionado es el soporte de esa promesa y del human-in-the-loop futuro.

**Independent Test**: El conjunto de prueba interrumpe una ejecucion en puntos
distintos (antes de un tool, durante, despues) y verifica que la reanudacion
parte del ultimo checkpoint y que 0 efectos se aplican dos veces.

**Acceptance Scenarios**:

1. **Given** una ejecucion interrumpida a mitad de camino, **When** se reanuda,
   **Then** parte del ultimo checkpoint con el contexto, la intencion y los
   tool results previos intactos.
2. **Given** una ejecucion que ya aplico un efecto persistente (por ejemplo,
   registro de feedback o cambio de perfil), **When** se reanuda por una
   desconexion, **Then** el efecto NO se aplica de nuevo (0 duplicados).
3. **Given** un fallo de modelo o de red, **When** la ejecucion termina en
   error, **Then** el estado registrado distingue fallido de interrumpido y
   permite reintentar desde el checkpoint sin partir de cero.
4. **Given** una sesion con una ejecucion activa, **When** llega una segunda
   solicitud de la misma sesion, **Then** se rechaza con un estado tipado y
   recuperable ("ejecucion en curso") y 0 ejecuciones corren en paralelo.

---

### User Story 3 - Aislamiento y continuidad entre requests (Priority: P0)

Como usuario, quiero que mi conversacion sea solo mia y que el sistema
recuerde donde voy entre una pregunta y la siguiente, para poder conversar con
el radar con naturalidad y sin riesgo de mezclar datos.

**Why this priority**: La continuidad entre requests es lo que hace
"conversacional" al radar, y el aislamiento por usuario/sesion es un requisito
de confianza del hito: 0 acceso cruzado, incluso con ids manipulados.

**Independent Test**: El conjunto de prueba reanuda sesiones entre requests y
verifica que cada thread esta aislado por usuario/sesion y que el acceso
cruzado se deniega.

**Acceptance Scenarios**:

1. **Given** una sesion de un usuario, **When** otro usuario intenta reanudarla
   o leerla con un id manipulado, **Then** se deniega el acceso (0 acceso
   cruzado).
2. **Given** un usuario con dos sesiones de distintos radares, **When** ambas
   se ejecutan, **Then** cada una conserva su propio contexto y ninguna filtra
   datos de la otra.
3. **Given** una sesion, **When** se envia un mensaje, **Then** la siguiente
   solicitud de la misma sesion retoma el contexto acumulado sin tener que
   repetir nada.
4. **Given** un cambio de schema del estado, **When** se despliega, **Then** los
   checkpoints existentes migran o se declaran incompatibles de forma
   documentada, sin perder la capacidad de reanudar.

---

### User Story 4 - Modelo centralizado con salidas estructuradas (Priority: P0)

Como equipo, quiero que toda llamada al modelo pase por un punto unico con
salidas estructuradas, timeout, reintentos acotados, registro de uso y
versiones de modelo/prompt/schema, para que el dominio nunca dependa de un
proveedor y las respuestas invalidas nunca lleguen al estado.

**Why this priority**: Es el seam de confianza del runtime: versionar modelo,
prompt y schema es lo que permite evaluar y revertir (H4.4) sin mutar runs
previos, y centralizar el adapter evita acoplar el dominio a un proveedor.

**Independent Test**: El conjunto de prueba fuerza respuestas invalidas,
timeouts y fallos, y verifica que el adapter los trata segun politica sin
filtrar proveedor al dominio y registrando uso.

**Acceptance Scenarios**:

1. **Given** una solicitud al modelo, **When** responde, **Then** el 100% de las
   respuestas se valida contra el schema permitido y las invalidas se rechazan
   o reintentan de forma acotada; 0 respuestas invalidas llegan al estado.
2. **Given** un modelo que no responde dentro del timeout, **When** se agota el
   reintento acotado, **Then** la ejecucion queda en error tipado y el usuario
   recibe un estado recuperable, sin bloqueos infinitos.
3. **Given** una llamada al modelo, **When** se registra, **Then** queda el uso
   (tokens), la version del modelo, la version del prompt y la version del
   schema, para poder reproducir y auditar.
4. **Given** el dominio, **When** se usa el modelo, **Then** 0 codigo de dominio
   conoce proveedores concretos: solo el adapter lo hace.

---

### User Story 5 - Ejecuciones auditables (Priority: P0)

Como equipo, quiero que cada ejecucion de la maquina de conversacion quede
registrada con version, latencia, estado, errores, uso y correlacion, para
poder diagnosticar, medir costos y auditar sin copiar PII.

**Why this priority**: La auditabilidad de graph runs y node/tool runs es
prerequisito de la operacion de beta (costos, errores, regresiones) y del
dashboard del agente (H4.4), y sostiene el principio de datos auditables.

**Independent Test**: El conjunto de prueba ejecuta escenarios de exito,
interrupcion y fallo y verifica que el 100% de los runs queda registrado con
los campos requeridos y correlacion estable.

**Acceptance Scenarios**:

1. **Given** una ejecucion exitosa, **When** termina, **Then** queda un graph
   run con version, estado, latencia, uso y su id de correlacion.
2. **Given** una ejecucion con fallos, **When** termina, **Then** quedan los
   errores resumidos y el estado distingue la causa sin necesidad de
   reconstruir el contenido de la conversacion.
3. **Given** un run con nodos y tools, **When** se registran, **Then** cada
   node/tool run queda vinculado al mismo graph run y correlacion.
4. **Given** una ejecucion con PII en mensajes, **When** se registra, **Then** 0
   PII innecesaria se copia a runs, logs o uso: solo referencias a los objetos
   persistentes.

### Edge Cases

- Desconexion en distintos puntos de la ejecucion (antes de un tool, durante,
  despues): la reanudacion parte del ultimo checkpoint y nunca reaplica
  efectos; 0 duplicados.
- Interrupcion a mitad de la generacion de una respuesta: 0 mensajes parciales
  se persisten; el fragmento queda en el checkpoint y la reanudacion completa
  el mensaje.
- Dos solicitudes simultaneas a la misma sesion: 0 ejecuciones paralelas; la
  segunda se rechaza con estado tipado y recuperable, sin encolar ni ignorar
  duplicados.
- Checkpoint con schema de una version anterior: migra o se declara
  incompatible de forma documentada; la reanudacion nunca pierde contexto
  silenciosamente.
- Respuesta del modelo invalida o fuera de schema: se rechaza o reintenta de
  forma acotada; 0 contenido invalido entra al estado ni a los mensajes.
- Timeout o fallo de red del proveedor: error tipado, reintento acotado y
  estado recuperable; 0 bucles infinitos y 0 costos descontrolados.
- Usuario con sesion de un radar archivado o pausado: la sesion refleja el
  estado del search profile, no acepta mensajes nuevos y no rompe la
  recuperacion del historial.
- Acceso cruzado con ids manipulados: denegado en el 100% de los casos.
- Mensajes que superan los limites de longitud o contenido permitido: se
  rechazan con error accionable y 0 HTML arbitrario se almacena.
- Cambio de version de modelo/prompt/schema: las versiones quedan registradas
  por llamada y los runs previos no se mutan.
- La retencion y limpieza de sesiones, mensajes y checkpoints sigue la
  politica de la clarificacion (cuenta + ventana corta de checkpoints),
  documentada y verificable.

## Requirements *(mandatory)*

### Functional Requirements

#### Sesiones y mensajes persistentes (UM-H4-001)

- **FR-001**: El sistema MUST persistir sesiones de chat como objetos de
  producto vinculados a un usuario y a un search profile, con estado y
  timestamps, y MUST permitir recuperar el historial en orden. El estado de la
  sesion MUST reflejar el de su search profile (activa, pausada, archivada) y
  una sesion pausada o archivada MUST NO aceptar mensajes nuevos, conservando
  el historial recuperable.
- **FR-002**: Cada mensaje MUST persistirse con rol, contenido tipado dentro
  del contenido permitido, estado y referencia a la ejecucion (graph run) que
  lo produjo; los mensajes creados MUST ser inmutables y todo cambio de estado
  MUST generar un evento de auditoria.
- **FR-003**: El contenido permitido MUST estar acotado (tipos definidos, sin
  HTML arbitrario ni media) y los mensajes MUST tener limites de longitud con
  errores accionables al superarlos.

#### Estado y topologia v1 (UM-H4-002)

- **FR-004**: El schema de estado de la sesion MUST separar mensajes, contexto,
  intencion, pending action, tool results y errores, y MUST estar versionado;
  el version MUST registrarse en cada checkpoint.
- **FR-005**: El 100% de los valores checkpointed MUST ser serializable
  (JSON-safe) y el schema MUST permitir migraciones de version sin perder la
  capacidad de reanudar.
- **FR-006**: El estado v1 MUST modelar la pending action (accion propuesta sin
  confirmar) de forma serializable, sin ejecutar su flujo de aprobacion, que se
  consume en H4.3.

#### Checkpointer persistente (UM-H4-003)

- **FR-007**: Los checkpoints MUST persistir entre requests y quedar aislados
  por usuario y sesion: el 100% de los intentos de reanudar o leer una sesion
  ajena (incluso con ids manipulados) MUST denegarse.
- **FR-008**: Los checkpoints MUST tener una politica de retencion y limpieza
  documentada y versionada: sesiones y mensajes MUST conservarse mientras
  exista la cuenta del usuario y borrarse con ella; los checkpoints MUST
  purgarse tras una ventana corta de inactividad (default 30 dias,
  parametrizable) sin alterar el historial persistido.
- **FR-009**: Un cambio de schema de checkpoint MUST migrar los existentes o
  declararlos incompatibles de forma documentada; 0 contextos se pierden
  silenciosamente.

#### Adapter de modelo (UM-H4-004)

- **FR-010**: Toda llamada al modelo MUST pasar por un adapter unico que
  centralice modelo, timeout, reintento acotado, uso y versiones; 0 codigo de
  dominio MUST conocer proveedores concretos.
- **FR-011**: Las salidas MUST ser estructuradas: el 100% de las respuestas se
  valida contra el schema permitido y las invalidas se rechazan o reintentan de
  forma acotada; 0 contenido invalido llega al estado.
- **FR-012**: Cada llamada MUST registrar la version del modelo, la version del
  prompt y la version del schema junto con el uso (tokens) y el estado, para
  auditar, reproducir y revertir.

#### Streaming y reanudacion (UM-H4-005)

- **FR-013**: La ejecucion MUST emitir eventos tipados a su consumidor (estado
  de la ejecucion, fragmentos de respuesta, resultados) con correlacion.
- **FR-014**: Una ejecucion interrumpida (desconexion, fallo de red o de
  modelo) MUST poder reanudarse desde el ultimo checkpoint, y MUST NO repetir
  efectos ya aplicados (0 duplicados). Un mensaje del asistente MUST persis-
  tirse solo cuando la respuesta se completa: los fragmentos intermedios viven
  en el checkpoint y la reanudacion los completa; 0 mensajes parciales se
  persisten en el historial.
- **FR-015**: El sistema MUST garantizar 0 ejecuciones paralelas por sesion:
  una segunda solicitud a una sesion con ejecucion activa MUST rechazarse con
  un estado tipado y recuperable ("ejecucion en curso"); la decision de
  reintentar queda en el cliente y no se encolan solicitudes.

#### Registro de ejecuciones (UM-H4-006)

- **FR-016**: El 100% de los graph runs MUST registrar version del schema/
  topologia, estado (pendiente, ejecutando, completado, fallido, interrumpido),
  latencia, errores resumidos, uso y correlacion.
- **FR-017**: El 100% de los node/tool runs MUST registrarse vinculados a su
  graph run con el mismo id de correlacion, su estado, latencia, errores y uso.
- **FR-018**: El registro de ejecuciones y logs MUST NO copiar PII innecesaria:
  solo referencias a objetos persistentes; 0 contenido de conversacion en
  registros tecnicos salvo lo estrictamente necesario.

#### Transversal

- **FR-019**: El incremento MUST integrar su harness de verificacion en
  `scripts/check.ps1` de acuerdo con la convencion de los incrementos previos.
- **FR-020**: Este incremento MUST NO exponer superficies de usuario ni
  contratos HTTP de chat nuevos: los contratos de streaming y UI son de H4.3 y
  las tools de H4.2.

### Key Entities

- **ChatSession**: conversacion persistente vinculada a usuario y search
  profile, con estado y timestamps; objeto de producto durable.
- **ChatMessage**: mensaje inmutable con rol, contenido tipado permitido,
  estado y lineage al graph run que lo produjo.
- **Checkpoint**: estado serializado y versionado de una ejecucion en un punto
  dado; aislado por usuario/sesion, con retencion y migracion.
- **GraphRun**: ejecucion completa de la maquina de conversacion con version,
  estado, latencia, errores, uso y correlacion.
- **NodeRun / ToolRun**: ejecuciones internas del graph con su propio estado,
  latencia, errores y uso, vinculadas al graph run.
- **ModelCall**: llamada al modelo con versiones de modelo/prompt/schema, uso y
  estado; no expone proveedor al dominio.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Conversacion persistente | UM-H4-001 |
| User Story 2 - Reanudacion sin duplicados | UM-H4-002, UM-H4-005 |
| User Story 3 - Aislamiento y continuidad | UM-H4-003 |
| User Story 4 - Adapter de modelo | UM-H4-004 |
| User Story 5 - Ejecuciones auditables | UM-H4-006 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H4-001 | FR-001, FR-002, FR-003 | US1.1-US1.4, SC-001 |
| UM-H4-002 | FR-004, FR-005, FR-006 | US2.1, SC-002 |
| UM-H4-003 | FR-007, FR-008, FR-009 | US3.1-US3.4, SC-003 |
| UM-H4-004 | FR-010, FR-011, FR-012 | US4.1-US4.3, SC-004 |
| UM-H4-005 | FR-013, FR-014, FR-015 | US2.1-US2.4, SC-005 |
| UM-H4-006 | FR-016, FR-017, FR-018 | US5.1-US5.4, SC-006 |
| Transversal (todos) | FR-019, FR-020 | SC-007 |

## Constitution Alignment *(mandatory)*

- **Persistent radar as product truth**: sesiones y mensajes son objetos de
  producto durables vinculados a search profiles, y los checkpoints son estado
  operativo que NUNCA reemplaza a busquedas, listings, recomendaciones,
  feedback ni eventos de auditoria. Sustenta el principio I.
- **Auditable deterministic matching**: el runtime registra graph runs y
  node/tool runs auditables y versiona modelo, prompt, schema y estado; las
  salidas estructuradas impiden que el LLM decida por fuera de esquemas
  permitidos. Sustenta el principio II.
- **Layered dependency direction**: el dominio no conoce proveedores de modelo,
  bases ni checkpoints; el adapter de modelo y el checkpointer son
  infraestructura detras de puertos. Sustenta el principio III.
- **Minimal verifiable change**: el incremento se limita a UM-H4-001 a
  UM-H4-006: 0 tools de producto, 0 contratos HTTP, 0 UI; todo cambio se
  verifica con pruebas y harness de acuerdo con la convencion del proyecto.
- **Data lineage, observability and trust**: las ejecuciones se correlacionan y
  registran sin copiar PII innecesaria; los mensajes trazan a sus runs y los
  runs a sus versiones. Sustenta el principio V.
- **Versioned prompts, models and schemas**: modelo, prompt, schema de salida y
  schema de estado se versionan por llamada y por checkpoint; los runs previos
  no se mutan y las versiones permiten evaluar y revertir (H4.4). Sustenta los
  principios II y V.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las sesiones traza a un usuario y a un search profile,
  el historial es recuperable en orden y 0 mensajes se reescriben tras crearse.
- **SC-002**: El 100% de los valores checkpointed es serializable y el schema
  de estado esta versionado; el 100% de los checkpoints registra su version.
- **SC-003**: El 100% de los intentos de reanudar o leer una sesion ajena se
  deniega; la retencion y limpieza se aplican segun politica documentada y 0
  contextos se pierden silenciosamente en migraciones.
- **SC-004**: El 100% de las respuestas del modelo se valida contra el schema
  permitido (0 invalidas al estado); el 100% de las llamadas registra versiones
  y uso; 0 codigo de dominio conoce proveedores concretos.
- **SC-005**: El 100% de las ejecuciones interrumpidas se reanuda desde el
  ultimo checkpoint con 0 efectos duplicados, 0 ejecuciones paralelas por
  sesion y 0 mensajes parciales persistidos en el historial.
- **SC-006**: El 100% de los graph runs y node/tool runs queda registrado con
  version, estado, latencia, errores, uso y correlacion, y 0 PII innecesaria se
  copia a registros tecnicos.
- **SC-007**: El harness de H4.1 corre en `scripts/check.ps1` y en CI; 0
  superficies de usuario, 0 contratos HTTP y 0 tools de producto nuevos en el
  incremento.

## Assumptions

- El alcance incluye exactamente UM-H4-001 a UM-H4-006 (Epica H4.1 - Runtime
  LangGraph). Las tools explicitas y permisos (H4.2), el comportamiento
  conversacional y la UI (H4.3) y los evals, costos y operacion (H4.4) quedan
  fuera y se especifican en sus propios incrementos.
- Depende de H1 (identidad, telemetria, correlacion), H2 (search profiles y
  radares persistentes) y H3 (matching, feedback) como maquinaria existente:
  el runtime la consume y NO la reimplementa. La identidad de usuario y el
  mapeo a search profiles ya existen (H1.3/H2.3).
- Una sesion de chat es una conversacion; un usuario puede tener varias
  sesiones, cada una ligada a un search profile del que es dueno. La sesion
  hereda el ownership del usuario.
- La reanudacion en H4.1 cubre desconexion y fallos de red/modelo. El
  human-in-the-loop (aprobar, editar, rechazar cambios) es de H4.3, pero el
  estado v1 modela la pending action para que H4.3 lo consuma sin cambiar el
  schema de forma retroactiva.
- Los eventos tipados del runtime son internos (consumidor en proceso); el
  contrato HTTP de streaming, reanudacion e historial es de H4.3.
- La eleccion del proveedor de modelo concreto se difiere al plan (ADR), como
  en incrementos previos; el adapter es agnostic de proveedor y cuenta con un
  fake local de prueba.
- Se permite una unica ejecucion activa por sesion: una segunda solicitud se
  rechaza con estado tipado y recuperable ("ejecucion en curso") y el cliente
  decide si reintenta; 0 colas y 0 duplicados ignorados.
- Las versiones de modelo, prompt y schema son inmutables por llamada y los
  runs previos no se mutan, consistente con el versionado de H3 (UM-H3-008).
- El contenido permitido de mensajes incluye texto y referencias tipadas a
  objetos de producto (listings, criterios, runs); sin HTML arbitrario, media
  ni PII innecesaria.
- La politica de retencion es: sesiones y mensajes persisten mientras exista
  la cuenta del usuario y se borran con ella (alineado con UM-H6-011); los
  checkpoints son estado operativo reanudable y se purgan tras una ventana
  corta de inactividad (default 30 dias, parametrizable) sin tocar el
  historial. El plan define la parametrizacion, el job de limpieza y su
  verificacion sin cambiar el alcance.
- El estado de la sesion refleja el de su search profile (activa, pausada,
  archivada) y una sesion pausada/archivada no acepta mensajes nuevos pero
  conserva el historial; 0 transiciones propias de sesion se inventan en H4.1.
- Un mensaje del asistente se persiste solo cuando la respuesta se completa;
  los fragmentos intermedios viven en el checkpoint y 0 mensajes parciales
  entran al historial.
- El idioma de casos, copy y registros es espanol (CABA), sobre el dataset
  controlado.
