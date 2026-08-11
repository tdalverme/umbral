# Feature Specification: Notificaciones y alertas proactivas

**Feature Branch**: `013-proactive-alerts`

**Created**: 2026-08-11

**Status**: Draft

**Input**: User description: "Especificacion del hito H5 - Proactividad controlada del backlog, con alcance exacto UM-H5-001 a UM-H5-020."

## Clarifications

### Session 2026-08-11

- Q1 (cadencia de entrega): ¿La entrega de alertas en beta es inmediata o en digest diario? → A: **Hibrida**. Price drops y nuevos matches con score por encima del umbral de la politica se entregan inmediatamente (sujeto a quiet hours y cooldown de fatiga); el resto de las oportunidades se agrupan en un digest diario (9:00, timezone del usuario). El digest requiere el agrupamiento de UM-H5-009, que pasa de P1 a P0.
- Q2 (alcance del email): ¿El email incluye solo la oportunidad o tambien un resumen del radar? → A: **Solo la oportunidad** con razones, riesgos, fuente, CTA (guardar/descartar/ver) y baja; 0 contenido no derivado de la decision persistida.
- Q3 (cobertura de canales): ¿Email solo o email + inbox web en la primera entrega? → A: **Email + inbox web** con una sola fuente de verdad (las mismas decisiones); el inbox es la superficie de producto y el email el empuje.

## Operational Definitions

- **Notificacion**: decision persistente y auditable de interrumpir al usuario con una oportunidad o evento relevante de su radar, derivada por codigo deterministico versionado y entregada por un canal (email o inbox web).
- **Preferencia de notificacion**: configuracion versionada por usuario y por busqueda (canales, timezone, quiet hours, frecuencia, umbral de score, estado) que acota que, cuando y por donde se entrega; cada cambio produce una version.
- **Planner de notificaciones**: motor puro y deterministico que recibe recommendation items, historial de entregas y policy snapshot, y devuelve decisiones con razon/codigo (nuevo match, baja de precio, pospuesto por quiet hours, descartado por fatiga, duplicado, etc.); 0 LLM en la decision.
- **Trigger**: condicion determinista que genera un candidato a notificar (nuevo match que supera hard filters/score/confianza, o baja de precio confirmada con umbral versionado).
- **Deduplicacion**: la misma oportunidad/evento/policy no genera mas de una decision de entrega; se registra la decision original y las re-intentos como duplicados.
- **Quiet hours**: ventana diaria configurada en la timezone del usuario durante la cual las entregas se posponen, agrupan o descartan segun politica, conservando la razon.
- **Fatiga**: limite determinista de entregas por ventana que aplica cooldowns cuando el usuario no interactua con las notificaciones previas.
- **Transactional outbox**: registro atomico de la decision y el mensaje a entregar; un worker puede reanudar sin perdida ni duplicacion.
- **Worker de entrega**: proceso idempotente que toma mensajes del outbox, entrega via el adapter del canal, registra el provider message id y maneja lease, timeout, backoff acotado y dead letter.
- **Inbox de notificaciones**: superficie web que lista las mismas decisiones que el email (una fuente de verdad), con estados leida/no leida y razon visible.
- **Unsubscribe token**: token acotado y expirable que permite desactivar preferencias desde el email sin iniciar sesion, auditando el cambio.

## Review and Measurement Protocol

- La puerta de salida de H5 cierra el hito `proactive-alerts` (UM-H5-001 a UM-H5-020): preferencias de notificacion modeladas y configurables, planner deterministico con triggers de nuevo match y baja de precio, deduplicacion, quiet hours, fatiga y digest, decisiones y eventos persistidos, outbox transaccional con worker idempotente, email adapter con templates grounded, inbox web, baja desde email, fallos operativos visibles e instrumentacion de entrega/vista/accion.
- El planner se verifica con casos golden deterministicos: la misma entrada (items, historial, policy) produce las mismas decisiones y razones, 0 duplicados, 0 entregas en quiet hours, cooldowns de fatiga aplicados, y cada decision referencia versiones de policy e inputs.
- La entrega se verifica con fallos simulados de proveedor y reinicios: el outbox confirma decision y mensaje atomicamente, el worker reanuda sin perdida ni duplicacion, los reintentos son acotados con backoff, y los mensajes fallidos quedan en dead letter consultable con causa.
- Los templates de email se verifican contra las decisiones persistidas: 0 afirmaciones no soportadas por la decision, enlaces validos y con contexto correcto, y baja accesible desde el propio email.
- El inbox web se verifica contra las mismas decisiones del email (una fuente de verdad): estados, paginacion, mark read y empty/error accesibles.
- La instrumentacion alimenta la metrica de beta (precision percibida) con eventos de entrega, vista y accion en las ventanas definidas.
- Los checks se integran al harness local (`scripts/check.ps1`) con la convencion de los incrementos previos (harness dedicado `check-alerts.ps1`); el incremento no cambia matching, scoring, ingesta ni el comportamiento conversacional.
- El E2E se verifica con casos new match, price drop, quiet hours, duplicado, fatiga, baja y fallo de proveedor cumpliendo las decisiones esperadas.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preferencias de alertas configurables (Priority: P0)

Como usuario de la beta, quiero decidir cuando y por donde me avisa Umbral, para controlar las interrupciones sin perder oportunidades.

**Why this priority**: Sin preferencias no hay politica de entrega respetable; es la base del planner (UM-H5-001/002).

**Independent Test**: Un usuario configura canales, timezone, quiet hours, frecuencia y umbral; cada cambio queda versionado y el planner respeta la ultima version.

**Acceptance Scenarios**:

1. **Given** un usuario con una busqueda activa, **When** configura alertas, **Then** puede definir canales (email, inbox), timezone, quiet hours, frecuencia y umbral de score, y cada cambio produce una version consultable.
2. **Given** un cambio de preferencias, **When** el usuario lo guarda, **Then** el planner usa la nueva version para decisiones nuevas sin reescribir decisiones previas.
3. **Given** preferencias pausadas o desactivadas, **When** hay oportunidades nuevas, **Then** no se entrega nada y la razon registrada es la preferencia.

### User Story 2 - Planner deterministico de notificaciones (Priority: P0)

Como sistema, quiero decidir que notificar con reglas puras y auditables, para garantizar 0 duplicados, quiet hours y fatiga.

**Why this priority**: Es el nucleo de H5 (UM-H5-003 a UM-H5-010); la precision percibida de beta depende de decisiones correctas.

**Independent Test**: Casos golden del planner: misma entrada produce las mismas decisiones con razon/codigo; 0 duplicados; quiet hours posponen; fatiga aplica cooldown.

**Acceptance Scenarios**:

1. **Given** un item nuevo que supera hard filters, score y confianza, **When** se corre el planner, **Then** se genera una decision de nuevo match con razon, salvo que este fuera de quiet hours, sea duplicado o aplique fatiga.
2. **Given** una baja de precio confirmada que supera el umbral versionado, **When** se corre el planner, **Then** se genera una decision de price drop con el cambio y el umbral referenciados.
3. **Given** la misma oportunidad procesada dos veces, **When** se corre el planner, **Then** la segunda ejecucion registra la decision como duplicado de la primera (0 entregas repetidas).
4. **Given** una entrega dentro de quiet hours, **When** se corre el planner, **Then** la decision queda pospuesta con razon y horario de reanudacion.
5. **Given** un usuario con entregas recientes sin interaccion, **When** se corre el planner, **Then** se aplica el cooldown de fatiga con su razon.

### User Story 3 - Entrega confiable por email (Priority: P0)

Como usuario, quiero recibir el email correcto una sola vez, para no perder oportunidades ni recibir duplicados.

**Why this priority**: Sin outbox y worker idempotente no hay entrega confiable (UM-H5-011 a UM-H5-014).

**Independent Test**: Fallos simulados del proveedor: el mensaje se reanuda sin perdida ni duplicacion, con reintentos acotados y dead letter consultable.

**Acceptance Scenarios**:

1. **Given** una decision de notificacion, **When** se persiste, **Then** decision y mensaje se confirman atomicamente en el outbox.
2. **Given** un fallo del proveedor al entregar, **When** el worker reintenta, **Then** los reintentos son acotados con backoff y el mensaje queda en dead letter con causa si se agotan.
3. **Given** un reinicio del worker a mitad de entrega, **When** se reanuda, **Then** no se pierde ni se duplica el mensaje (idempotencia por provider message id).
4. **Given** un email entregado, **When** el usuario lo abre, **Then** el template muestra la oportunidad con razones, riesgos, fuente, acciones y la baja, todo derivado de la decision persistida (0 afirmaciones inventadas).

### User Story 4 - Centro de notificaciones web (Priority: P0)

Como usuario, quiero ver las notificaciones en la web con su razon, para decidir sin abrir el email.

**Why this priority**: Complementa el email con la misma fuente de verdad (UM-H5-015/016).

**Acceptance Scenarios**:

1. **Given** decisiones entregadas por email, **When** el usuario abre el centro, **Then** ve las mismas notificaciones con razon, estado y enlace al contexto correcto.
2. **Given** una notificacion, **When** el usuario la marca como leida, **Then** el estado cambia y persiste sin duplicar la decision.
3. **Given** un usuario sin notificaciones, **When** abre el centro, **Then** ve el estado vacio con explicacion.

### User Story 5 - Baja y control desde email (Priority: P0)

Como usuario, quiero desactivar alertas desde el propio email sin login, para controlar las interrupciones de inmediato.

**Why this priority**: Requisito de respeto al usuario y de terminos de beta (UM-H5-017).

**Acceptance Scenarios**:

1. **Given** un email de alerta, **When** el usuario usa el enlace de baja, **Then** la preferencia se actualiza sin login, el cambio queda auditado y el token expira.
2. **Given** un token de baja reutilizado o vencido, **When** se procesa, **Then** se rechaza sin cambiar preferencias y se registra el evento.

### User Story 6 - Operacion y medicion (Priority: P0)

Como equipo, quiero ver fallos, reintentos y metricas de entrega/vista/accion, para operar la beta y medir precision percibida.

**Why this priority**: Sin instrumentacion no hay go/no-go de beta (UM-H5-018 a UM-H5-020).

**Acceptance Scenarios**:

1. **Given** mensajes fallidos, **When** un operador consulta, **Then** ve backlog, causa, intentos y la accion segura, sin reenviar duplicados.
2. **Given** una notificacion entregada, **When** el usuario la ve o acciona, **Then** se emiten eventos versionados de entrega/vista/accion que alimentan precision percibida.

### Edge Cases

- Oportunidad nueva durante quiet hours: queda pospuesta, no descartada, con razon y horario.
- Baja de precio dentro de la misma ventana que un new match: se deduplica y entrega una sola vez con la razon de mayor prioridad.
- Usuario sin timezone configurada: usa el default de la region (America/Argentina/Buenos_Aires) documentado en preferencias.
- Proveedor de email caido por mas tiempo que el backoff: dead letter con causa y alerta operativa; la decision no se pierde.
- Inbox y email entregan la misma decision: la vista no genera una segunda entrega.
- Frecuencia digest con oportunidades multiples: agrupa sin alterar scores individuales y conserva cada razon.
- Usuario con multiples busquedas: las preferencias y cooldowns se aplican por busqueda y la fatiga global se suma con politica documentada.

## Requirements *(mandatory)*

### Functional Requirements

#### Preferencias de notificacion (UM-H5-001)

- FR-H5-001: El sistema mantiene preferencias de notificacion versionadas por usuario y por busqueda con canal (email, inbox), timezone, quiet hours, frecuencia, umbral de score y estado (activo/pausado/desactivado); cada cambio produce una version inmutable.
- FR-H5-002: El usuario puede ver y editar sus preferencias desde la web con explicacion de impacto y opcion de desactivar sin ocultar el radar (UM-H5-002).

#### Planner deterministico (UM-H5-003 a UM-H5-010)

- FR-H5-003: El planner expone una interfaz pura que recibe recommendation items, historial de entregas y policy snapshot, y devuelve decisiones con razon/codigo (UM-H5-003).
- FR-H5-004: El trigger de nuevo match considera solo items nuevos que superan hard filters, score y confianza de la politica (UM-H5-004).
- FR-H5-005: El trigger de baja de precio exige un cambio confirmado, un umbral versionado y relevancia actual para la busqueda (UM-H5-005).
- FR-H5-006: La misma oportunidad/evento/policy no genera mas de una entrega; las repeticiones se registran como duplicados con referencia a la decision original (UM-H5-006).
- FR-H5-007: Quiet hours y timezone posponen, agrupan o descartan segun politica sin perder la razon (UM-H5-007).
- FR-H5-008: Fatiga y frecuencia consideran entregas/vistas/feedback recientes y aplican cooldowns deterministicos; la cadencia hibrida entrega inmediato price drops y new matches de score alto, y agrupa el resto en el digest diario (UM-H5-008).
- FR-H5-009: Diversidad y digest agrupan las oportunidades del dia sin alterar scores individuales y conservando cada razon; es parte de la cadencia hibrida por decision de producto (UM-H5-009, P0).
- FR-H5-010: Cada decision persiste policy, inputs, razon, estado y vinculacion al recommendation item (UM-H5-010).

#### Entrega (UM-H5-011 a UM-H5-014)

- FR-H5-011: Decision y mensaje se confirman atomicamente en un transactional outbox (UM-H5-011).
- FR-H5-012: El worker de entrega es idempotente con lease, timeout, backoff acotado, dead letter y provider message id (UM-H5-012).
- FR-H5-013: El adapter de email centraliza proveedor, redaccion, unsubscribe, metadata permitida y clasificacion de errores; local usa fake/recording (UM-H5-013).
- FR-H5-014: Los templates de email muestran oportunidad, razones, riesgos, fuente, CTA, preferencias y baja; 0 afirmaciones no persistidas (UM-H5-014).

#### Inbox y baja (UM-H5-015 a UM-H5-017)

- FR-H5-015: El inbox lista notificaciones paginadas con estado leida/no leida, razon y enlace al contexto correcto con ownership (UM-H5-015).
- FR-H5-016: El centro de notificaciones web refleja las mismas decisiones que el email, con mark read y estados accesibles (UM-H5-016).
- FR-H5-017: El enlace de baja usa un token acotado y expirable que desactiva sin login y audita el cambio (UM-H5-017).

#### Operacion y medicion (UM-H5-018 a UM-H5-020)

- FR-H5-018: El operador ve fallos y reintentos (backlog, causa, intentos, accion segura) sin reenviar duplicados (UM-H5-018).
- FR-H5-019: La entrega, vista y accion emiten eventos versionados que alimentan precision percibida e irrelevancia (UM-H5-019).
- FR-H5-020: El E2E cubre new match, price drop, quiet hours, duplicado, fatiga, baja y fallo de proveedor (UM-H5-020).

### Non-Functional Requirements

- NFR-H5-001: 0 notificaciones duplicadas en condiciones normales y de reintento.
- NFR-H5-002: 0 entregas fuera de quiet hours salvo politica explicita.
- NFR-H5-003: 0 afirmaciones en email no soportadas por la decision persistida.
- NFR-H5-004: 0 PII en eventos y telemetria; el contenido del email solo viaja por el adapter autorizado.
- NFR-H5-005: Cada decision y entrega es reconstruible desde sus versiones (policy, preferencias, item, intentos).

## Success Criteria *(mandatory)*

- Un usuario configura sus alertas en menos de 2 minutos desde la web y el cambio aplica a la siguiente decision.
- 100% de las decisiones del planner son deterministicas (misma entrada, misma salida y razon) y auditables (policy + inputs + item referenciados).
- 0 notificaciones duplicadas y 0 entregas en quiet hours en el E2E y en operacion de beta.
- El 100% de los emails entregados son reconstruibles desde la decision persistida; 0 afirmaciones no soportadas.
- El 100% de los mensajes pasan por el outbox y el worker reanuda sin perdida ni duplicacion ante fallos y reinicios simulados.
- La baja desde email desactiva las alertas sin login en el 100% de los casos con token valido, y 0 cambios con tokens vencidos.
- Los eventos de entrega/vista/accion alimentan la metrica de precision percibida de beta (>= 35%) con ventanas definidas.

## Key Entities

- **NotificationPreferences**: preferencias versionadas por usuario/busqueda (canales, timezone, quiet hours, frecuencia, umbral, estado).
- **NotificationPolicy**: politica versionada e inmutable (triggers, umbrales, cooldowns, ventanas) usada por el planner.
- **NotificationDecision**: decision persistida con policy, inputs, razon/codigo, estado y vinculo al recommendation item y a la decision original (dedupe).
- **OutboxMessage**: mensaje a entregar confirmado atomicamente con la decision, estado, intentos y provider message id.
- **DeliveryAttempt**: intento de entrega con lease, timeout, resultado y causa.
- **NotificationInboxItem**: vista web de la decision con estado leida/no leida.
- **NotificationEvent**: evento versionado de entrega/vista/accion para metricas.

## Assumptions

- La beta usa los canales email (Resend, mismo proveedor transaccional del ADR 0003) e inbox web; el email es el canal primario y el inbox la misma fuente de verdad.
- Defaults de preferencias iniciales: timezone America/Argentina/Buenos_Aires, quiet hours 22:00-08:00, cadencia hibrida (inmediato para price drop y new match con score sobre el umbral de politica; digest diario 9:00 para el resto), umbral de score por politica versionada.
- Los triggers consideran solo recommendation items persistidos del ultimo run publicado (0 calculos ad-hoc del planner).
- El scheduler de los workers corre con el scheduler simple existente del repo; Dagster/Prefect solo si el lineage lo exige.
- El email contiene solo la oportunidad (razones, riesgos, fuente, CTA, baja); el inbox web muestra las mismas decisiones.
- La diversidad/digest (UM-H5-009) es parte de la cadencia hibrida y queda en el camino critico (P0).
