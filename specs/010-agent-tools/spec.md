# Feature Specification: Tools explicitas y permisos

**Feature Branch**: `010-agent-tools`

**Created**: 2026-08-09

**Status**: Draft

**Input**: User description: "Arranquemos con la especificacion de la epica H4.2 - Tools explicitas y permisos del backlog, con alcance exacto UM-H4-007 a UM-H4-016."

## Clarifications

### Session 2026-08-09

- Q: ¿Las propuestas de cambio de perfil (propose_search_profile_update →
  apply_search_profile_update) son objetos durables y auditables en H4.2 o
  solo estado de sesion? → A: Son objetos durables y auditables: cada
  propuesta persiste con su diff validado, impacto y estado
  (pendiente/aprobada/rechazada), con expiracion y un solo uso, y se conserva
  mientras exista la cuenta del usuario (alineado con UM-H6-011). El flujo
  interactivo de edicion/rechazo con UI sigue siendo de H4.3, pero la
  propuesta como objeto de producto vive en H4.2.
- Q: ¿Todos los cambios de perfil requieren confirmacion explicita o solo los
  sensibles (presupuesto, zona, hard filters, radio, contradicciones)? → A:
  Todos los cambios de perfil requieren confirmacion explicita: no existe
  aplicacion directa de cambios, ni siquiera de bajo impacto; el contrato
  propose → confirm → apply es uniforme.
- Q: ¿find_matches es estrictamente de solo lectura o puede disparar una
  recomputacion? → A: Es estrictamente de solo lectura: devuelve los
  recommendation items persistidos del ultimo run publicado y declara estado
  explicito si no hay run o esta desactualizado; nunca dispara computacion,
  costos ni mutaciones. La recomputacion ocurre por la maquinaria existente
  (H3-030) cuando el perfil cambia.
- Q: Cuando una propuesta de cambio de perfil queda pendiente y el perfil
  cambia por otra via antes de aplicarla (otra sesion o edicion directa del
  radar), ¿que hace el sistema al aplicar? → A: La rechaza por obsolescencia:
  la propuesta registra la version del perfil sobre la que se creo; si el
  perfil cambio antes de aplicar, apply la marca como rechazada con error
  tipado y 0 efectos, y el usuario debe proponer de nuevo sobre el perfil
  vigente.
- Q: ¿Quien ejecuta la transicion de una propuesta a "rechazada" en H4.2, si
  el flujo interactivo de aprobar/editar/rechazar con UI es de H4.3? → A:
  Solo transiciones deterministas por politica en H4.2: pendiente → aprobada
  via apply con confirmacion, y pendiente → rechazada por obsolescencia o
  vencimiento (expiracion). El rechazo interactivo explicito del usuario y la
  edicion de propuestas llegan con H4.3; 0 caminos interactivos se inventan
  en este incremento.
- Q: ¿Que tipos de feedback puede registrar el chat en H4.2 con la tool de
  feedback? → A: Solo like/dislike con razones opcionales: es lo que la
  politica de H3.3 reconoce como señal de aprendizaje (like/dislike con
  razones ligadas a conceptos) y lo que tiene sentido expresar en
  conversacion. save, dismiss y contacted quedan para la UI estructurada
  existente (H3.3); la tool rechaza tipos fuera de su contrato.

## Operational Definitions

- **Tool (herramienta del agente)**: contrato explicito y versionado que el
  agente conversacional puede invocar para operar sobre objetos de producto
  persistentes (perfil, matches, explicaciones, feedback, contexto urbano).
  Nunca es acceso libre a la base: toda tool valida identidad, alcance del
  radar, schema, timeout, idempotencia, autorizacion y redaccion de salidas.
- **Contrato y politica comun de tools**: conjunto de reglas uniformes que toda
  tool debe cumplir: identidad del usuario, search scope (radar de la sesion),
  esquema de entradas/salidas validado, timeout, idempotency key para tools
  mutantes, autorizacion deny-by-default y politica de redaccion de outputs.
- **Search scope**: alcance de datos que una tool puede tocar: el search
  profile de la sesion y los objetos de producto (listings, runs, feedback,
  signals) visibles para ese radar. Nada fuera del scope es accesible, ni
  siquiera con ids manipulados.
- **Redaccion de outputs**: politica por la que una tool devuelve solo los
  campos y volumenes permitidos (limites de tamaño, campos necesarios, 0 PII
  innecesaria) en lugar de volcar contenido completo.
- **Propuesta de cambio de perfil**: resultado de propose_search_profile_update:
  un diff validado contra el esquema del perfil, su impacto esperado y si
  requiere confirmacion. Es un objeto durable y auditable: persiste con
  estado (pendiente/aprobada/rechazada), expiracion y un solo uso, vinculado
  a la sesion y al radar que la origino. No modifica el perfil por si misma.
- **Confirmacion**: aprobacion explicita del usuario de la propuesta
  especifica (identificada por proposal id) antes de aplicarla. Sin
  confirmacion, ninguna tool mutante produce efectos persistentes.
- **Idempotency key**: clave provista por el invocador para que repetir una
  operacion mutante con la misma clave no duplique efectos.
- **Recommendation run/item**: resultado persistido y congelado del motor de
  matching (H2/H3): items con score, orden, profile snapshot, score version y
  evidencia. La unica fuente de scores del chat.
- **Explicacion persistida**: desglose generado y guardado por el scoring
  (H3.2): score version, profile snapshot, feature snapshot, criterios,
  evidence refs, confianza y datos faltantes. El chat la recupera, nunca la
  inventa.
- **Comparacion estructurada**: comparacion generada y persistida por el motor
  (H3.2) sobre dimensiones homogeneas, con faltantes y tradeoffs; no inventa
  un ganador generativo.
- **Propuesta de aprendizaje**: propuesta de preference fact/criterion derivada
  del feedback por politica determinista (H3.3); nunca se aplica
  automaticamente.
- **Signal urbana versionada**: dato de contexto urbano (transporte, cafes,
  espacios verdes) con fuente, fecha, geometria y algoritmo registrados (H3.1).

## Review and Measurement Protocol

- La puerta de salida de H4.2 es que el agente conversacional pueda operar
  sobre el radar mediante tools explicitas y permitidas —leer perfil, proponer
  y confirmar cambios, encontrar y explicar matches, comparar, registrar
  feedback y consultar contexto urbano— sin acceso libre a la base, sin
  ranking generativo y con salidas redactadas, antes de abordar el
  comportamiento conversacional y la UI (H4.3).
- El contrato comun se verifica confirmando que el 100% de las tools valida
  identidad, search scope, schema, timeout, idempotencia y redaccion de
  salidas, y que las invocaciones quedan registradas como tool runs con la
  misma correlacion que su graph run (infraestructura de H4.1).
- El aislamiento se verifica probando que 0 datos de radares ajenos son
  accesibles: acceso cruzado con ids manipulados denegado en el 100% de los
  casos, en cada tool.
- La confirmacion se verifica probando que 0 cambios de perfil se aplican sin
  confirmacion explicita, que repetir una aplicacion con la misma idempotency
  key no duplica efectos y que cada aplicacion versiona el perfil y dispara
  una recomputacion que preserva el run anterior (H3-030).
- El grounding se verifica confirmando que el 100% de los matches y
  explicaciones que devuelve el chat provienen de objetos persistentes: 0
  scores inventados y 0 afirmaciones sin evidencia interna.
- El feedback se verifica probando idempotencia (repetir no duplica; cambiar
  decision genera compensacion trazable) y que las propuestas de aprendizaje
  nunca se aplican solas.
- El contexto urbano (P1) se verifica confirmando que solo se consultan
  signals versionadas y que la precision geografica autorizada se respeta (no
  se revelan coordenadas mas precisas que las permitidas).
- La suite de aislamiento y abuso (UM-H4-016) se verifica como gate del
  incremento: acceso cruzado, args manipulados, prompt injection, outputs
  excesivos y tools mutantes sin confirmacion quedan cubiertos por pruebas.
- Este incremento se integra al harness local (`scripts/check.ps1`) de acuerdo
  con la convencion de los incrementos previos y no expone superficies nuevas
  de usuario ni contratos HTTP (los contratos de chat streaming son de H4.3).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Contrato y politica comun de tools (Priority: P0)

Como equipo de producto, quiero que todas las herramientas del chat compartan
un mismo contrato y politica (identidad, alcance del radar, esquema, timeout,
idempotencia, autorizacion y redaccion de salidas), para que ninguna pueda
operar fuera de su radar ni devolver contenido no autorizado.

**Why this priority**: Es la base de confianza de la epica: sin un contrato
comun, cada tool seria una puerta distinta a los datos y UM-H4-016 no tendria
superficie estable que probar.

**Independent Test**: El conjunto de prueba invoca cada tool con identidad
valida, ids ajenos, entradas fuera de schema y solicitudes de volumen excesivo,
y verifica que la politica comun se cumple en el 100% de los casos.

**Acceptance Scenarios**:

1. **Given** una sesion con su search profile, **When** cualquier tool se
   invoca, **Then** se valida identidad y search scope antes de ejecutar
   cualquier lectura o efecto.
2. **Given** una tool con entradas fuera de schema o con timeout, **When** se
   invoca, **Then** se rechaza o falla con error tipado y accionable y queda
   registrada como tool run vinculada a su graph run; 0 efectos parciales.
3. **Given** una tool que devuelve datos de producto, **When** responde,
   **Then** la salida esta redactada: solo campos permitidos, limites de
   tamaño y 0 PII innecesaria.
4. **Given** una tool mutante, **When** se invoca sin idempotency key o con
   una repetida, **Then** la politica de idempotencia se aplica y repetir la
   misma operacion no duplica efectos.

---

### User Story 2 - Consultar el perfil del radar (Priority: P0)

Como usuario, quiero preguntarle al chat que criterios tiene mi radar para
confirmar que refleja mi intencion de busqueda.

**Why this priority**: Leer el perfil autorizado es la primera operacion de
confianza: el chat solo puede hablar del radar del usuario y de nada mas.

**Independent Test**: El conjunto de prueba consulta el perfil desde la sesion
correcta y desde sesiones ajenas (con ids manipulados) y verifica que solo el
perfil autorizado se devuelve.

**Acceptance Scenarios**:

1. **Given** una sesion ligada a un search profile, **When** se invoca la
   tool de lectura de perfil, **Then** devuelve el snapshot vigente y los
   criterios ejecutables necesarios de ese radar, y nada de otros radares.
2. **Given** un intento de leer el perfil de otro radar o usuario con ids
   manipulados, **When** se invoca la tool, **Then** se deniega el acceso
   (0 acceso cruzado).
3. **Given** un radar pausado o archivado, **When** se consulta el perfil,
   **Then** la respuesta declara el estado del radar sin presentarlo como
   activo.

---

### User Story 3 - Proponer y confirmar cambios de radar (Priority: P0)

Como usuario, quiero pedirle al chat que ajuste mi radar y revisar o confirmar
el cambio antes de que se aplique, para no terminar con criterios que no
aprobe.

**Why this priority**: Cambiar criterios modifica el matching futuro: la
confirmacion explicita es el guardrail de la epica y el tema central de la
suite de abuso (tools mutantes sin confirmacion).

**Independent Test**: El conjunto de prueba propone cambios validos e
invalidos, intenta aplicarlos sin confirmacion, con propuestas ajenas y
repetidos, y verifica que 0 cambios se aplican sin confirmacion y que ninguna
aplicacion se duplica.

**Acceptance Scenarios**:

1. **Given** un pedido de cambio de criterios, **When** se propone, **Then**
   se produce un diff validado contra el esquema del perfil, con su impacto
   esperado y la necesidad de confirmacion, y queda una propuesta durable y
   auditada en estado pendiente; el perfil NO se modifica en este paso.
2. **Given** una propuesta confirmada por el usuario, **When** se aplica con
   la confirmacion y una idempotency key, **Then** el perfil queda versionado
   (nueva version, conservando las previas), la propuesta pasa a aprobada (un
   solo uso) y se dispara una recomputacion que preserva el run anterior.
3. **Given** una aplicacion sin confirmacion, con una propuesta ajena, vencida,
   ya usada o basada en una version de perfil que ya no es la vigente, **When**
   se intenta aplicar, **Then** se rechaza con error tipado y 0 efectos
   persistentes; en el caso de obsolescencia la propuesta queda rechazada y el
   usuario debe proponer de nuevo.
4. **Given** una aplicacion repetida con la misma idempotency key, **When** se
   reenvia, **Then** no se duplican efectos ni versiones de perfil.
5. **Given** cualquier cambio de criterios, incluso de bajo impacto, **When**
   se solicita, **Then** el cambio requiere confirmacion explicita: no existe
   aplicacion directa sin pasar por propose → confirm → apply.

---

### User Story 4 - Encontrar y entender matches (Priority: P0)

Como usuario, quiero que el chat me muestre oportunidades reales y me explique
por que matchean con evidencia, para decidir con confianza sin salir del chat.

**Why this priority**: Es el corazon del valor del radar conversacional y el
lugar donde el principio "nunca scores inventados" se prueba en la practica.

**Independent Test**: El conjunto de prueba solicita matches y explicaciones
de runs publicados y de radares sin runs, y verifica que el 100% de las
respuestas proviene de objetos persistentes y que las explicaciones citan la
evidencia guardada.

**Acceptance Scenarios**:

1. **Given** un radar con un run publicado, **When** se piden matches, **Then**
   la tool devuelve los recommendation items persistentes de ese run con su
   orden y datos esenciales; 0 scores inventados.
2. **Given** un radar sin run publicado o con run desactualizado, **When** se
   piden matches, **Then** la respuesta declara el estado explicito (0 items o
   frescura) en lugar de inventar resultados.
3. **Given** un item del radar de la sesion, **When** se pide su explicacion,
   **Then** se recupera la explicacion persistida (score version, profile
   snapshot, criterios, evidence refs) y se declaran los datos faltantes y la
   incertidumbre.
4. **Given** un item ajeno al search scope, **When** se intenta explicar,
   **Then** se deniega el acceso (0 acceso cruzado).
5. **Given** una explicacion sin evidencia suficiente, **When** se presenta,
   **Then** el chat declara la falta de evidencia y no completa hechos (0
   afirmaciones no soportadas).

---

### User Story 5 - Comparar oportunidades en contexto (Priority: P0)

Como usuario, quiero comparar oportunidades dentro de mi radar con el
comparador estructurado, para sopesar tradeoffs sin que el chat invente un
ganador.

**Why this priority**: La comparacion es una decision de producto: usar solo
la comparacion estructurada persistida evita que el chat produzca rankings
generativos.

**Independent Test**: El conjunto de prueba compara listings del mismo radar,
listings fuera de contexto y mas listings del limite permitido, y verifica la
validacion y la ausencia de ganador generativo.

**Acceptance Scenarios**:

1. **Given** listings pertenecientes al radar de la sesion, **When** se pide
   comparar, **Then** se usa la comparacion estructurada con dimensiones
   homogeneas, faltantes y tradeoffs, hasta el limite definido.
2. **Given** un listing fuera del contexto permitido, **When** se intenta
   comparar, **Then** se rechaza con error accionable y 0 datos de otros
   radares se exponen.
3. **Given** una comparacion, **When** se presenta, **Then** no se inventa un
   ganador generativo: el resultado se apoya en la comparacion persistida.

---

### User Story 6 - Registrar feedback y aprender (Priority: P0)

Como usuario, quiero dar feedback desde el chat y que el sistema proponga
aprender de el, sin cambiar mi radar sin que yo lo confirme.

**Why this priority**: El feedback del chat alimenta la precision percibida de
beta y el aprendizaje controlado; la idempotencia evita duplicar eventos que
ensucian metricas y propuestas.

**Independent Test**: El conjunto de prueba registra el mismo feedback dos
veces, cambia una decision previa y verifica idempotencia, compensacion
trazable y ausencia de cambios automaticos.

**Acceptance Scenarios**:

1. **Given** un usuario que da like o dislike a un item desde el chat, **When**
   se registra, **Then** queda un evento de feedback inmutable vinculado al
   item, la sesion y el usuario; repetir la misma accion no duplica eventos.
   Las razones opcionales quedan ligadas al evento como insumo cualitativo de
   las senales de aprendizaje.
2. **Given** un cambio de decision sobre un item, **When** el usuario la
   cambia, **Then** se genera un evento nuevo o una compensacion trazable
   (nunca se reescribe el evento previo).
3. **Given** feedback con señal suficiente segun politica, **When** se
   registra, **Then** la tool devuelve la propuesta de aprendizaje cuando
   corresponde, sin aplicarla automaticamente.
4. **Given** feedback sobre un item fuera del search scope, **When** se
   intenta registrar, **Then** se rechaza (0 acceso cruzado).

---

### User Story 7 - Consultar contexto urbano (Priority: P1)

Como usuario, quiero preguntar por el entorno de una zona (transporte, cafes,
espacios verdes) usando datos versionados y respetando la precision
geografica autorizada.

**Why this priority**: El contexto urbano agrega valor a las decisiones pero
solo es confiable si las signals tienen fuente y fecha y no se revelan
coordenadas mas precisas que las permitidas.

**Independent Test**: El conjunto de prueba consulta zonas con y sin signals y
verifica que solo se usan datos versionados y la precision autorizada.

**Acceptance Scenarios**:

1. **Given** una zona con signals urbanas, **When** se consulta, **Then** se
   devuelven solo signals versionadas con fuente, fecha, geometria y
   algoritmo registrados.
2. **Given** una consulta de contexto urbano, **When** se responde, **Then**
   la precision geografica autorizada se respeta (0 coordenadas mas precisas
   que las permitidas).
3. **Given** una zona sin datos, **When** se consulta, **Then** la respuesta
   declara la falta de datos en lugar de inventarlos.

---

### User Story 8 - Aislamiento y abuso de tools (Priority: P0)

Como equipo de confianza, quiero pruebas que demuestren que las tools no
pueden cruzarse entre usuarios, ejecutar cambios sin confirmacion ni ser
manipuladas por prompts o argumentos, para sostener el denegar-por-defecto.

**Why this priority**: Es el gate de seguridad de la epica: sin esta suite,
ninguna tool deberia considerarse terminada, porque todas operan datos de
producto reales.

**Independent Test**: El conjunto de prueba ejecuta una bateria adversaria
sobre el 100% de las tools (acceso cruzado, args manipulados, prompt
injection, outputs excesivos y mutacion sin confirmacion) y exige 0 fallos.

**Acceptance Scenarios**:

1. **Given** cualquier tool, **When** se intenta acceder a objetos de otro
   usuario o radar con ids manipulados, **Then** se deniega en el 100% de los
   casos.
2. **Given** argumentos manipulados o fuera de schema, **When** se invoca una
   tool, **Then** se rechazan con error tipado y 0 efectos.
3. **Given** contenido malicioso en mensajes o listings (prompt injection),
   **When** el agente procesa, **Then** no se habilitan tools no pedidas, no
   se exponen datos ajenos ni se ejecutan mutaciones sin confirmacion.
4. **Given** una solicitud de volumen excesivo de salida, **When** una tool
   responde, **Then** la redaccion de outputs la acota y 0 PII innecesaria se
   filtra.
5. **Given** un intento de mutacion sin confirmacion, **When** se invoca una
   tool mutante, **Then** 0 efectos persistentes se producen.

### Edge Cases

- Acceso cruzado con ids manipulados en cada tool (perfil, runs, items,
  feedback, signals): denegado en el 100% de los casos.
- Radar pausado o archivado: las tools de lectura declaran el estado y las
  mutantes no aceptan cambios nuevos, conservando la recuperacion de
  historial y runs.
- Radar sin run publicado o con run desactualizado: find_matches declara
  estado explicito; 0 resultados inventados.
- Propuesta ajena, vencida, ya usada o de otra sesion: apply la rechaza con
  error tipado; 0 efectos.
- Propuesta basada en una version de perfil que ya no es la vigente (el radar
  cambio por otra sesion o por edicion directa): apply la rechaza por
  obsolescencia con error tipado y el usuario debe proponer de nuevo; 0
  cambios sobre un contexto superado.
- Propuesta vencida sin aplicar: pasa a rechazada por politica (vencimiento)
  sin efectos en el perfil; el rechazo interactivo del usuario y la edicion
  de propuestas son de H4.3.
- Repetir apply con la misma idempotency key: 0 duplicados de versiones,
  runs ni eventos.
- Cambio de decision de feedback (like → dislike): evento nuevo o
  compensacion trazable; 0 reescrituras del evento previo.
- Feedback con tipo fuera del contrato de la tool (save, dismiss, contacted
  desde el chat): rechazado con error tipado y 0 efectos; esos tipos
  pertenecen a la UI estructurada existente.
- Prompt injection en mensajes o contenido de listings: 0 tools no pedidas,
  0 datos ajenos, 0 mutaciones sin confirmacion.
- Salida que excede los limites de redaccion: acotada a campos y volumen
  permitidos; 0 PII innecesaria.
- Tool sin idempotency key en operacion mutante: rechazada o ejecutada segun
  la politica definida, sin efectos duplicados.
- Timeout o fallo de una tool: error tipado, tool run registrado y estado de
  ejecucion recuperable; 0 efectos parciales.
- Contexto urbano sin datos o con precision menor a la solicitada: declara la
  falta o la precision disponible sin inventar.

## Requirements *(mandatory)*

### Functional Requirements

#### Contrato y politica comun de tools (UM-H4-007)

- **FR-001**: El 100% de las tools MUST cumplir un contrato comun y versionado:
  identidad del usuario, search scope (radar de la sesion), esquema de
  entradas/salidas, timeout, politica de idempotencia para tools mutantes,
  autorizacion deny-by-default y politica de redaccion de outputs.
- **FR-002**: Toda invocacion de tool MUST validar identidad y search scope
  antes de cualquier lectura o efecto: 0 acceso a objetos fuera del radar de
  la sesion, incluso con ids manipulados.
- **FR-003**: Las salidas de toda tool MUST estar redactadas: solo campos
  permitidos, limites de tamaño definidos y 0 PII innecesaria; 0 volumenes
  completos de datos se devuelven al agente.
- **FR-004**: El 100% de las invocaciones de tools MUST registrarse como tool
  runs vinculados a su graph run con la misma correlacion, su estado,
  latencia, errores y uso; los fallos MUST ser tipados y recuperables, con 0
  efectos parciales.

#### Lectura del perfil (UM-H4-008)

- **FR-005**: La tool de lectura de perfil MUST devolver solo el search
  profile autorizado de la sesion: el snapshot vigente y los criterios
  ejecutables necesarios, declarando el estado del radar (activo, pausado,
  archivado) sin presentar uno pausado/archivado como activo.
- **FR-006**: Cualquier intento de leer un perfil ajeno (ids manipulados,
  otra sesion u otro usuario) MUST denegarse con error tipado; 0 datos de
  otros radares se devuelven.

#### Propuesta de cambio de perfil (UM-H4-009)

- **FR-007**: La tool de propuesta MUST producir, para cualquier cambio de
  criterios solicitado, un diff validado contra el esquema del perfil, el
  impacto esperado y la necesidad de confirmacion; MUST NO persistir cambios
  de perfil por si misma. Todo cambio de perfil, incluso de bajo impacto,
  MUST requerir confirmacion explicita: 0 aplicaciones directas sin pasar por
  propose → confirm → apply.
- **FR-008**: Toda propuesta MUST ser un objeto durable y auditable: persiste
  con diff, impacto, estado (pendiente/aprobada/rechazada), vigencia
  (expiracion) y uso (un solo uso), vinculada a la sesion y al search profile
  que la origino, y se conserva mientras exista la cuenta del usuario. Toda
  propuesta MUST registrar la version del perfil sobre la que se creo.
- **FR-009**: Una propuesta sin confirmacion MUST NO producir cambios
  persistentes en el perfil. Las unicas transiciones de estado en H4.2 MUST
  ser deterministas por politica: pendiente → aprobada (solo via apply con
  confirmacion) y pendiente → rechazada (solo por obsolescencia o vencimiento);
  el rechazo interactivo del usuario y la edicion de propuestas MUST
  postergarse a H4.3, sin efectos en el perfil.

#### Aplicacion de cambio de perfil (UM-H4-010)

- **FR-010**: La tool de aplicacion MUST requerir una propuesta valida
  (misma sesion, vigente, sin usar y basada en la version vigente del
  perfil), una confirmacion explicita del usuario sobre esa propuesta y una
  idempotency key; sin esos elementos MUST rechazarse con 0 efectos. Si el
  perfil cambio desde la version base de la propuesta, apply MUST rechazarla
  por obsolescencia: la marca como rechazada con error tipado y 0 efectos.
  Toda propuesta aplicada MUST pasar a aprobada y quedar como de un solo uso.
- **FR-011**: Toda aplicacion valida MUST versionar el perfil (nueva version
  conservando las previas) y MUST disparar una recomputacion que preserva el
  run anterior (H3-030).
- **FR-012**: Repetir una aplicacion con la misma idempotency key MUST NO
  duplicar efectos ni versiones; el resultado de la aplicacion ya procesada
  es recuperable.

#### Busqueda de matches (UM-H4-011)

- **FR-013**: La tool de matches MUST devolver solo recommendation items
  persistentes del run publicado para el radar de la sesion, con su orden y
  datos esenciales; 0 scores inventados. La tool MUST ser de solo lectura:
  0 recomputaciones, costos o mutaciones se disparan desde el chat; la
  recomputacion ocurre por la maquinaria existente cuando el perfil cambia
  (H3-030).
- **FR-014**: Cuando no exista run publicado o el run este desactualizado,
  la tool MUST declarar el estado explicito (0 items o frescura) en lugar de
  producir resultados.

#### Explicacion de matches (UM-H4-012)

- **FR-015**: La tool de explicacion MUST recuperar la explicacion persistida
  del item (score version, profile snapshot, feature snapshot, criterios,
  evidence refs, confianza) y MUST declarar los datos faltantes y la
  incertidumbre.
- **FR-016**: La explicacion MUST NO contener afirmaciones sin evidencia
  interna: si falta evidencia, se declara; 0 hechos se completan.

#### Comparacion de listings (UM-H4-013)

- **FR-017**: La tool de comparacion MUST validar que todos los listings
  pertenecen al contexto permitido de la sesion (el radar de la sesion) y
  respetar el limite de la comparacion estructurada definido en H3.2.
- **FR-018**: El resultado MUST apoyarse en la comparacion estructurada
  persistida (dimensiones homogeneas, faltantes, tradeoffs); 0 ganador
  generativo se inventa.

#### Registro de feedback (UM-H4-014)

- **FR-019**: La tool de feedback MUST registrar eventos inmutables e
  idempotentes: repetir la misma accion MUST NO duplicar eventos, y cambiar
  una decision MUST generar un evento nuevo o una compensacion trazable sin
  reescribir el previo. El contrato de la tool MUST cubrir like/dislike con
  razones opcionales (senal de aprendizaje segun politica H3.3); tipos fuera
  de ese contrato (save, dismiss, contacted) MUST rechazarse con error tipado
  y 0 efectos, ya que pertenecen a la UI estructurada.
- **FR-020**: Cuando la politica lo indique, la tool MUST devolver la
  propuesta de aprendizaje correspondiente; 0 cambios se aplican
  automaticamente.

#### Contexto urbano (UM-H4-015, P1)

- **FR-021**: La tool de contexto urbano MUST consultar solo signals
  versionadas (fuente, fecha, geometria, algoritmo registrados) y MUST
  respetar la precision geografica autorizada: 0 coordenadas mas precisas que
  las permitidas y 0 datos inventados cuando no existen.

#### Aislamiento y abuso de tools (UM-H4-016)

- **FR-022**: Una suite de pruebas adversarias MUST cubrir el 100% de las
  tools: acceso cruzado con ids manipulados (denegado en el 100% de los
  casos), argumentos fuera de schema (rechazados con 0 efectos), prompt
  injection (0 tools no pedidas, 0 datos ajenos, 0 mutaciones sin
  confirmacion), outputs excesivos (acotados por redaccion) y tools mutantes
  sin confirmacion (0 efectos persistentes).
- **FR-023**: Las pruebas de aislamiento y abuso MUST formar parte del gate
  del incremento y del harness de verificacion, sin depender del LLM: el
  resultado de cada caso adversario es deterministico.

#### Transversal

- **FR-024**: El incremento MUST integrar su harness de verificacion en
  `scripts/check.ps1` de acuerdo con la convencion de los incrementos
  previos.
- **FR-025**: Este incremento MUST NO exponer superficies de usuario ni
  contratos HTTP de chat nuevos: los contratos de streaming y la UI
  conversacional son de H4.3.

### Key Entities

- **ToolContract**: definicion versionada del contrato de cada tool (nombre,
  schema de entradas/salidas, search scope, timeout, idempotencia,
  autorizacion, redaccion); la base de la politica comun.
- **SearchProfileUpdateProposal**: objeto durable y auditable de propuesta de
  cambio de perfil: diff validado, impacto, estado (pendiente/aprobada/
  rechazada), vigencia, uso y version del perfil base sobre la que se creo;
  vinculado a la sesion y al radar que la origino, conservado mientras exista
  la cuenta del usuario. En H4.2 las transiciones de estado son solo
  deterministas: aprobada via apply y rechazada por obsolescencia o
  vencimiento.
- **PendingAction**: accion propuesta sin confirmar en el estado de la sesion
  (modelada en H4.1, FR-006) que las tools de propuesta/aplicacion consumen
  o pueblan.
- **SearchProfile / ProfileSnapshot / Criterion**: objetos existentes (H2.3,
  H3.1) que las tools de perfil leen y versionan; nunca duplicados por el
  chat.
- **RecommendationRun / RecommendationItem**: objetos existentes (H2.3/H3.2)
  que find_matches devuelve; la unica fuente de scores.
- **Explanation / EvidenceRef / CriterionEvaluation**: objetos existentes
  (H3.2) que explain_match recupera; 0 explicaciones generadas en el chat.
- **StructuredComparison**: comparacion persistida (H3.2) que compare_listings
  consume.
- **FeedbackEvent / LearningProposal**: objetos existentes (H3.3) que
  record_feedback crea o devuelve; el contrato del chat cubre like/dislike con
  razones opcionales, y save/dismiss/contacted quedan en la UI estructurada.
- **UrbanSignal**: signal urbana versionada existente (H3.1) que
  search_urban_context consulta.
- **ToolRun**: registro de ejecucion de una tool (infraestructura H4.1, fila
  con `node_kind` de tool) vinculado a su graph run.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Contrato y politica comun | UM-H4-007 |
| User Story 2 - Consultar el perfil del radar | UM-H4-008 |
| User Story 3 - Proponer y confirmar cambios | UM-H4-009, UM-H4-010 |
| User Story 4 - Encontrar y entender matches | UM-H4-011, UM-H4-012 |
| User Story 5 - Comparar oportunidades | UM-H4-013 |
| User Story 6 - Registrar feedback y aprender | UM-H4-014 |
| User Story 7 - Consultar contexto urbano | UM-H4-015 |
| User Story 8 - Aislamiento y abuso de tools | UM-H4-016 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H4-007 | FR-001, FR-002, FR-003, FR-004 | US1.1-US1.4, SC-001 |
| UM-H4-008 | FR-005, FR-006 | US2.1-US2.3, SC-002 |
| UM-H4-009 | FR-007, FR-008, FR-009 | US3.1, SC-003 |
| UM-H4-010 | FR-010, FR-011, FR-012 | US3.2-US3.4, SC-004 |
| UM-H4-011 | FR-013, FR-014 | US4.1-US4.2, SC-005 |
| UM-H4-012 | FR-015, FR-016 | US4.3-US4.5, SC-005 |
| UM-H4-013 | FR-017, FR-018 | US5.1-US5.3, SC-006 |
| UM-H4-014 | FR-019, FR-020 | US6.1-US6.4, SC-007 |
| UM-H4-015 | FR-021 | US7.1-US7.3, SC-008 |
| UM-H4-016 | FR-022, FR-023 | US8.1-US8.5, SC-009 |
| Transversal (todos) | FR-024, FR-025 | SC-010 |

## Constitution Alignment *(mandatory)*

- **Persistent radar as product truth**: las tools operan exclusivamente sobre
  objetos de producto persistentes (perfiles, runs, items, explicaciones,
  feedback, signals) y las propuestas de cambio de perfil son objetos
  durables y auditados con ciclo de vida; 0 oportunidades ni decisiones viven
  solo en el chat y queda trazabilidad de por que cambio el radar. Sustenta
  el principio I.
- **Auditable deterministic matching**: find_matches devuelve items
  persistidos y explain_match cita evidencia guardada; 0 ranking o scores
  generativos y la suite de abuso es determinista. Sustenta el principio II.
- **Layered dependency direction**: las tools son contratos explicitos y
  permitidos sobre puertos de aplicacion/dominio; 0 acceso libre a la base y
  el agente nunca decide rankings. Sustenta el principio III.
- **Minimal verifiable change**: el incremento se limita a UM-H4-007 a
  UM-H4-016: 0 contratos HTTP de chat y 0 UI (H4.3); toda tool se verifica
  con pruebas y harness segun la convencion del proyecto.
- **Data lineage, observability and trust**: cada invocacion queda registrada
  como tool run con correlacion y sin PII innecesaria; las salidas se redactan
  y el feedback es idempotente para no ensuciar metricas. Sustenta el
  principio V.
- **Versioned prompts, models and schemas**: el contrato de tools y el
  esquema de entradas/salidas son versionados; las propuestas y aplicaciones
  de perfil versionan y preservan run previo. Sustenta los principios II y V.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las tools cumple el contrato comun (identidad,
  scope, schema, timeout, idempotencia, autorizacion, redaccion) y el 100%
  de las invocaciones queda registrada como tool run con correlacion; 0
  salidas sin redactar y 0 fallos no tipados.
- **SC-002**: El 100% de los intentos de leer un perfil ajeno se deniega; la
  tool de perfil devuelve solo datos del radar de la sesion y declara su
  estado.
- **SC-003**: El 100% de los cambios propuestos produce una propuesta durable
  y auditada (diff validado, impacto, estado pendiente) sin modificar el
  perfil; 0 cambios se aplican sin confirmacion y todo cambio, incluso de
  bajo impacto, requiere confirmacion explicita. Las unicas transiciones de
  estado en el incremento son deterministas: aprobada via apply y rechazada
  por obsolescencia o vencimiento.
- **SC-004**: El 100% de las aplicaciones validas versiona el perfil, pasa la
  propuesta a aprobada (un solo uso) y dispara recomputacion preservando el
  run anterior; 0 duplicados al repetir con la misma idempotency key, 0
  aplicaciones sin confirmacion y 0 aplicaciones sobre perfiles que cambiaron
  desde la version base de la propuesta (obsolescencia rechazada con error
  tipado).
- **SC-005**: El 100% de los matches y explicaciones del chat provienen de
  objetos persistentes: 0 scores inventados, 0 afirmaciones sin evidencia y
  estados explicitos ante ausencia o desactualizacion de runs; find_matches
  es de solo lectura y nunca dispara recomputaciones desde el chat.
- **SC-006**: El 100% de las comparaciones valida el contexto permitido y el
  limite definido; 0 ganadores generativos.
- **SC-007**: El 100% de los feedbacks registrados es idempotente (0
  duplicados al repetir, compensacion trazable al cambiar decision) y las
  propuestas de aprendizaje nunca se aplican automaticamente; el contrato del
  chat cubre solo like/dislike con razones opcionales y 0 tipos fuera de
  contrato producen efectos.
- **SC-008**: El 100% de las consultas de contexto urbano usa solo signals
  versionadas y respeta la precision geografica autorizada; 0 datos
  inventados.
- **SC-009**: La suite de aislamiento y abuso (acceso cruzado, args
  manipulados, prompt injection, outputs excesivos, mutacion sin confirmacion)
  pasa el 100% de los casos de forma determinista y forma parte del gate del
  incremento.
- **SC-010**: El harness de H4.2 corre en `scripts/check.ps1` y en CI; 0
  superficies de usuario y 0 contratos HTTP de chat nuevos en el incremento.

## Assumptions

- El alcance incluye exactamente UM-H4-007 a UM-H4-016 (Epica H4.2 - Tools
  explicitas y permisos). El comportamiento conversacional y la UI (H4.3) y
  los evals, costos y operacion (H4.4) quedan fuera y se especifican en sus
  propios incrementos.
- Depende de la maquinaria existente y NO la reimplementa: identidad y
  permisos (H1.3), search profiles y radares persistentes (H2.3), matching y
  runs (H3.2), explicaciones y comparacion estructurada (H3.2), feedback y
  propuestas de aprendizaje (H3.3), contexto urbano versionado (H3.1) y
  runtime con sesiones, checkpoints, tool runs y adapter de modelo con
  salidas estructuradas (H4.1).
- Las tools son internas del agente: se invocan por el orquestador conversa-
  cional con salidas estructuradas; no se exponen contratos HTTP propios en
  este incremento (los contratos de chat son de H4.3). El alcance del agente
  queda acotado por su sesion: usuario + search profile.
- UM-H4-015 (search_urban_context) es P1 pero se incluye en el incremento,
  consistente con la convencion de incrementos previos que incluyeron items
  P1 de su epica; su verificacion es parte del harness.
- La redaccion de outputs cubre campos permitidos, limites de tamaño y 0 PII
  innecesaria; los valores concretos (limites, timeouts) se definen en el
  plan, no en el spec.
- La politica comun es deny-by-default: toda tool parte sin acceso y cada
  permiso se concede por contrato; 0 acceso cruzado en el 100% de los casos.
- La confirmacion de cambios de perfil es explicita y esta vinculada a la
  propuesta especifica; todo cambio, incluso de bajo impacto, pasa por
  propose → confirm → apply y las propuestas son durables, auditables, con
  expiracion y un solo uso (retencion por cuenta, alineado con UM-H6-011).
- find_matches es estrictamente de solo lectura: 0 recomputaciones desde el
  chat; los resultados dependen de la frescura de los runs existentes y la
  recomputacion ocurre por la maquinaria existente (H3-030) cuando el perfil
  cambia. En cualquier caso, 0 scores inventados.
- El ciclo de vida de las propuestas en H4.2 es determinista: pendiente →
  aprobada (solo via apply confirmado) y pendiente → rechazada (solo por
  obsolescencia o vencimiento). El rechazo interactivo del usuario y la
  edicion de propuestas dependen de compilar intencion y de la UI, por lo que
  son de H4.3; la ventana de vencimiento se define en el plan como parametro
  de politica.
- Las tools no deciden ranking ni aplican cambios: el agente invoca tools y
  el resultado siempre proviene de codigo determinista versionado (scoring,
  comparacion, aprendizaje, recomputacion).
- El idioma de casos, copy y registros es espanol (CABA), sobre el dataset
  controlado.
