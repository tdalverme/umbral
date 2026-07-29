# Feature Specification: Foundation Runtime

**Feature Branch**: `001-foundation-runtime`

**Created**: 2026-07-28

**Status**: Ready for planning

**Input**: User description: "Implementar el incremento `foundation-runtime` del backlog, con alcance exacto UM-H1-001 a UM-H1-012 y UM-H1-016 a UM-H1-020."

## Clarifications

### Session 2026-07-28

- Q: ¿Qué acceso debe permitirse a los ambientes preview y producción antes de implementar identidad? → A: Ambos ambientes permanecen restringidos mediante controles del entorno; sólo la comprobación básica de vida puede ser pública y no revela detalles internos.
- Q: ¿Cómo debe responder el runtime cuando falla una dependencia que sólo afecta a una de sus superficies? → A: Readiness se evalúa por superficie; sólo la superficie afectada queda no disponible y la degradación general permanece visible.
- Q: ¿Cuándo deben considerarse idénticos dos trabajos que reciben la misma clave idempotente? → A: Cuando coinciden el tipo de trabajo, el objetivo lógico y la clave idempotente.
- Q: ¿Qué debe ocurrir al volver a solicitar un trabajo ya terminado con la misma identidad idempotente? → A: Se devuelve el estado y resultado existentes sin crear intentos ni efectos nuevos; una reejecución intencional requiere una clave nueva.
- Q: ¿Qué información pueden registrar por defecto los logs y trazas en preview y producción? → A: Sólo metadata permitida: correlación, operación, estado, duración, versión y tipo o estado del trabajo; se excluyen cuerpos, valores de headers y parámetros.

## Operational Definitions

- **Superficies canónicas**: `web`, `api`, `worker` y `scheduler`. La interfaz
  web sólo presenta y consume contratos; la API recibe solicitudes y coordina
  casos de uso; el worker ejecuta trabajo asíncrono; el scheduler activa
  ocurrencias planificadas. Reglas internas y contratos no dependen de estas
  superficies ni de adaptadores externos.
- **Ambientes canónicos**: `local`, `preview` y `production`. Sus diferencias
  se expresan sólo mediante configuración y recursos asignados; una versión
  candidata no puede recompilarse entre preview y producción.
- **Dependencia crítica**: dependencia cuya indisponibilidad impide a una
  superficie cumplir su responsabilidad principal de forma segura. Una
  dependencia degradable permite continuar esa responsabilidad sin pérdida de
  integridad. El plan MUST publicar la matriz por superficie y el criterio de
  promoción MUST rechazar estados degradados o no disponibles.
- **Objetivo lógico de un trabajo**: identificador canónico, estable,
  no sensible e inmutable del recurso o alcance sobre el que opera un tipo de
  trabajo. Cada tipo de trabajo MUST definir su normalización antes de aceptar
  ejecuciones.
- **Fallo transitorio**: condición explícitamente clasificada como recuperable
  sin cambiar la entrada ni la identidad del trabajo. Fallos de validación,
  invariantes o permisos son permanentes; fallos no clasificados terminan la
  ejecución y requieren revisión. El límite de intentos y el backoff MUST estar
  declarados por tipo de trabajo.
- **Smoke test**: nombre canónico de la prueba mínima posterior a una
  promoción. **Rollback**: nombre canónico de la restauración de la versión
  operativa anterior. Cuando los datos no admiten rollback seguro se usa una
  compensación documentada o se detiene la promoción.
- **Un efecto lógico**: para el trabajo de referencia, una única mutación
  confirmada y un único registro auditable asociados con la identidad
  idempotente; mensajes, intentos y reintentos no cuentan como efectos.
- **Identidad de versión de objeto**: combinación de objeto lógico y versión
  inmutable generada por la aplicación. Repetirla con el mismo hash, tamaño y
  tipo devuelve la versión existente; repetirla con contenido o metadata
  distintos es un conflicto. Sólo versiones verificadas son observables.
- **Cambio de contrato compatible**: adición opcional que no modifica la
  interpretación de campos, estados, errores o comportamiento publicados. La
  eliminación o renombre, el cambio de tipo o semántica, un campo antes
  opcional que pasa a obligatorio y un nuevo resultado que un consumidor
  exhaustivo no pueda procesar son incompatibles.

## Review and Measurement Protocol

- El inventario de configuración por ambiente MUST indicar para cada valor:
  propietario, fuente, superficie consumidora, obligatoriedad, formato,
  clasificación secreta o pública, validación y exposición permitida.
- Preview y production no pueden aceptar credenciales de ejemplo, secretos
  vacíos, endpoints locales, transporte sin cifrar hacia dependencias externas
  ni un modo de acceso no restringido. Los diagnósticos nombran el campo y la
  regla incumplida, nunca su valor.
- Antes de identidad, sólo identidades de servicio y personas responsables de
  entrega autorizadas por el control del ambiente pueden acceder a preview o
  production. La promoción se bloquea si ese control falta, no puede evaluarse
  o permite rutas externas distintas de la excepción aprobada. La evidencia
  registra ambiente, regla evaluada, resultado, tiempo y versión, sin
  credenciales.
- Si se habilita la excepción pública de vida, responde únicamente HTTP 200 y
  `{"status":"alive"}` con `Content-Type: application/json` y
  `Cache-Control: no-store`; no acepta parámetros ni incluye headers propios
  con detalles internos. El plan puede elegir no exponerla públicamente.
- La postura temporal termina sólo cuando el incremento de identidad demuestra
  autenticación y autorización deny-by-default en preview y production. Hasta
  esa evidencia, los controles de ambiente siguen siendo obligatorios.
- La base visual se evalúa contra WCAG 2.2 nivel AA: estructura y nombres
  accesibles, contraste mínimo de 4.5:1 para texto normal y 3:1 para texto
  grande y componentes, foco visible, operación completa por teclado y respeto
  de reducción de movimiento. El conjunto mínimo incluye tipografía, tokens de
  color/espaciado/radio, botón, campo con etiqueta, tarjeta, alerta, indicador
  de carga y estados disabled/focus/error.
- El reloj de inicio local comienza con un checkout limpio y Python, Node,
  Docker y sus gestores ya instalados; termina cuando las cuatro superficies
  reportan vida, readiness y la misma versión, y el harness finaliza sin fallos.
- Los conjuntos finitos de configuración, dependencias prohibidas,
  compatibilidad de contratos y drift se versionan como fixtures del harness.
  Cada criterio de “100%” se calcula sobre todos los casos declarados en esas
  fixtures.
- El tiempo de rollback comienza al declarar fallido el smoke test y termina
  cuando la versión previa vuelve a estar lista y queda evidencia registrada.
  El tiempo de diagnóstico comienza al entregar una correlación de un fallo y
  termina al identificar superficie, ejecución, versión y estado causal.
- El responsable de entrega decide y registra rollback o detención; cualquier
  compensación de datos requiere además aprobación registrada del responsable
  de datos. La ausencia de una ruta previamente ensayada bloquea production.
- Cada ambiente admite una sola promoción mutante a la vez. Una segunda
  promoción concurrente se rechaza antes de migrar o desplegar y registra la
  versión que mantiene el lock; nunca espera de forma ambigua ni modifica
  parcialmente el ambiente.
- La política de recuperación de production tiene como responsables a
  operación de entrega y datos, realiza copias como mínimo cada 12 horas,
  conserva 35 días y ensaya una restauración al crear la política y luego
  mensualmente. Local y preview son reconstruibles y quedan fuera del respaldo
  periódico, pero sus migraciones y contratos deben poder recrearlos.
- El dimensionamiento, alta disponibilidad, recuperación regional y objetivos
  de carga de beta se decidirán en UM-H6-018 a UM-H6-020. Este incremento sólo
  valida las cuatro superficies, diez envíos duplicados del trabajo de
  referencia, una activación solapada y el conjunto de objetos de contrato.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Iniciar una aplicación coherente (Priority: P1)

Como integrante del equipo de Umbral, quiero iniciar las superficies de servicio
y web desde un entorno documentado, con configuración validada, límites
arquitectónicos comprobables y un contrato compartido, para poder desarrollar
los incrementos de producto sobre una base consistente.

**Why this priority**: Sin una aplicación ejecutable y contratos coherentes no
se pueden construir, integrar ni demostrar de forma confiable los incrementos
posteriores.

**Independent Test**: Una persona que no preparó el entorno puede seguir la
documentación, iniciar ambas superficies, consultar salud y versión, y ejecutar
los checks de arquitectura y contratos en 15 minutos o menos.

**Acceptance Scenarios**:

1. **Given** un entorno nuevo con todos los valores requeridos, **When** una
   persona sigue el procedimiento de inicio, **Then** las superficies de
   servicio y web quedan disponibles y reportan la misma versión de producto.
2. **Given** que falta un valor obligatorio o existe una configuración
   insegura, **When** se intenta iniciar una superficie, **Then** el inicio se
   detiene con un diagnóstico accionable sin revelar secretos.
3. **Given** un cambio incompatible en el contrato publicado, **When** su
   consumidor no fue actualizado o versionado, **Then** la verificación falla
   antes de que el cambio pueda promoverse.
4. **Given** una dependencia prohibida entre responsabilidades internas,
   **When** se ejecuta el harness, **Then** el cambio es rechazado e identifica
   la dirección inválida.
5. **Given** la base visual inicial, **When** se inspeccionan tema, tipografía,
   estados de interacción y componentes base mínimos, **Then** usan roles semánticos
   y cumplen los checks de accesibilidad acordados sin incluir pantallas de
   producto especulativas.

---

### User Story 2 - Evolucionar datos con trazabilidad (Priority: P2)

Como integrante del equipo de desarrollo, quiero crear y evolucionar estructuras
persistentes mediante cambios controlados y metadata común de identidad y
auditoría, para evitar divergencias, escrituras parciales y pérdida de
trazabilidad.

**Why this priority**: Los siguientes incrementos dependen de datos durables y
auditables; introducirlos sin una evolución controlada volvería frágiles las
migraciones y los objetos de producto.

**Independent Test**: Desde un entorno vacío y desde la versión anterior se
puede aplicar la evolución inicial, comprobar capacidades requeridas y ausencia
de drift, crear un registro de referencia con metadata común y rechazar una
actualización basada en una versión obsoleta.

**Acceptance Scenarios**:

1. **Given** un entorno persistente vacío, **When** se aplica la evolución
   inicial, **Then** queda en la versión esperada y confirma las capacidades
   geográficas y vectoriales requeridas.
2. **Given** un entorno en la versión anterior, **When** se aplica el cambio
   controlado, **Then** llega al mismo estado esperado sin drift.
3. **Given** un fallo durante una operación transaccional, **When** la operación
   termina, **Then** no queda un estado parcial observable.
4. **Given** un registro persistente de referencia, **When** se crea o modifica,
   **Then** conserva identidad, timestamps, versión optimista, actor, origen y
   correlación.
5. **Given** dos actualizaciones basadas en la misma versión, **When** la
   segunda intenta sobrescribir la primera, **Then** se rechaza el cambio
   obsoleto y se preserva la versión confirmada.

---

### User Story 3 - Ejecutar trabajo durable y recuperable (Priority: P3)

Como persona operadora, quiero ejecutar trabajos repetibles y almacenar objetos
versionados con estado, integridad y una política de recuperación, para poder
reanudar fallos sin duplicar efectos ni perder evidencia.

**Why this priority**: La importación, el enriquecimiento y las recomendaciones
futuras necesitarán ejecución asíncrona y snapshots durables antes de procesar
datos reales.

**Independent Test**: Un trabajo de referencia puede programarse, fallar,
reintentarse y repetirse diez veces con la misma identidad produciendo un único
efecto lógico; un conjunto de objetos puede escribirse y recuperarse por versión
con integridad comprobada.

**Acceptance Scenarios**:

1. **Given** diez solicitudes con el mismo tipo de trabajo, objetivo lógico y
   clave idempotente, **When** se procesan, **Then** existe un único efecto
   lógico y un resultado final consultable.
2. **Given** un fallo transitorio, **When** el trabajo se reintenta dentro del
   límite configurado, **Then** termina correctamente o queda en un estado
   terminal accionable con el historial de intentos.
3. **Given** ejecuciones programadas que se superponen, **When** se activa el
   mismo trabajo, **Then** la superposición no duplica el efecto.
4. **Given** dos versiones de un objeto, **When** se recupera cada una,
   **Then** devuelve exactamente su contenido, tipo e integridad registrados.
5. **Given** una pérdida de datos dentro de la ventana de recuperación acordada,
   **When** una persona sigue el procedimiento documentado, **Then** puede
   restaurar datos persistentes y objetos dentro del RTO y explicar el punto de
   recuperación alcanzado.
6. **Given** una ejecución en estado terminal, **When** se vuelve a solicitar
   el mismo tipo de trabajo y objetivo lógico con la misma clave idempotente,
   **Then** se devuelve el estado y resultado registrados sin crear un intento
   ni un efecto nuevos.

---

### User Story 4 - Diagnosticar y promover una versión (Priority: P4)

Como persona responsable de una entrega, quiero verificar salud, readiness,
correlación y versión, y promover el mismo artefacto por preview y producción
con smoke test y rollback, para operar cambios recuperables y explicables.

**Why this priority**: Una base local no cumple la puerta de salida del
incremento si no puede observarse, verificarse y promoverse de forma
controlada.

**Independent Test**: Una versión candidata recorre preview y producción con el
mismo identificador, supera el harness y el smoke test, permite diagnosticar un
fallo representativo y puede volver a la versión anterior en 15 minutos o
menos.

**Acceptance Scenarios**:

1. **Given** una solicitud que origina un trabajo y una escritura de objeto,
   **When** se consulta la evidencia operativa, **Then** el recorrido completo
   puede reconstruirse con la misma correlación usando sólo metadata permitida,
   sin cuerpos, valores de headers, parámetros ni otro contenido sensible.
2. **Given** la pérdida de una dependencia crítica para una superficie,
   **When** se consulta readiness, **Then** esa superficie informa que no está
   lista en menos de 60 segundos, las superficies no afectadas conservan su
   estado y la degradación general queda visible, mientras la comprobación
   básica de vida sigue sin producir efectos.
3. **Given** una versión candidata, **When** se promueve, **Then** preview y
   producción reciben el mismo artefacto versionado y cada promoción ejecuta
   los cambios de datos y el smoke test acordado.
4. **Given** un smoke test fallido, **When** se activa el rollback, **Then** la
   versión operativa anterior se restaura en 15 minutos o menos y el resultado
   queda registrado.
5. **Given** un fallo representativo en una solicitud o trabajo, **When** otra
   persona usa estado, logs y trazas, **Then** identifica el componente y la
   ejecución afectados en 15 minutos o menos.
6. **Given** que identidad de producto todavía no está implementada, **When**
   una solicitud externa intenta acceder a preview o producción, **Then** el
   control del entorno la rechaza salvo que consulte la comprobación básica de
   vida, cuya respuesta no revela detalles internos.

### Edge Cases

- Valores de configuración vacíos, mal formados, contradictorios o presentes en
  el ambiente equivocado deben tratarse como inválidos, sin imprimir su
  contenido sensible.
- Un consumidor atrasado no debe aceptar silenciosamente un cambio incompatible
  del contrato actual.
- Una evolución de datos interrumpida o dos promociones concurrentes no deben
  dejar un esquema parcialmente aplicado ni ambiguo.
- Un trabajo que falla después de producir el efecto pero antes de confirmar su
  estado debe poder reanudarse sin repetir el efecto.
- Reintentos masivos, activaciones programadas superpuestas y reinicios del
  runtime no deben evadir el límite de intentos ni la identidad del trabajo.
- La misma clave idempotente usada para tipos de trabajo u objetivos lógicos
  diferentes no debe provocar una colisión entre ejecuciones independientes.
- Una ejecución terminal no debe reactivarse al repetir su identidad; una
  reejecución intencional debe usar una clave nueva para conservar trazabilidad.
- Una escritura de objeto cuyo contenido no coincide con su integridad declarada
  debe rechazarse; una falla entre metadata y contenido debe compensarse o
  quedar explícitamente recuperable.
- La indisponibilidad del receptor de telemetría no debe corromper el estado de
  producto ni provocar exposición de contenido sensible; el problema debe
  quedar visible para operación.
- Las comprobaciones de salud repetidas o concurrentes no deben crear datos,
  trabajos ni conexiones durables innecesarias.
- Un rollback que no pueda revertir datos de forma segura debe usar una
  compensación documentada y detener la promoción.
- Los mensajes de error, URLs, atributos operativos y excepciones deben aplicar
  el mismo filtrado de secretos y datos personales que los logs normales.
- Un atributo operativo que no pertenece a la lista permitida debe omitirse por
  defecto, aunque no haya sido clasificado explícitamente como sensible.
- Una configuración ausente o incorrecta del control de acceso al entorno debe
  impedir la promoción; no debe compensarse confiando en que todavía no existen
  datos de producto.
- La falla de una dependencia usada por una sola superficie no debe retirar del
  servicio a las demás ni ocultarse como un estado totalmente saludable.

## Requirements *(mandatory)*

### Functional Requirements

#### Aplicación ejecutable y contratos

- **FR-001**: El sistema MUST separar responsabilidades de interfaz de producto,
  coordinación de casos de uso, reglas internas, adaptadores externos y
  ejecución en segundo plano, y MUST rechazar automáticamente dependencias que
  contradigan la dirección establecida.
- **FR-002**: El incremento MUST ofrecer superficies mínimas de servicio y web
  que puedan iniciarse y verificarse juntas sin incorporar funciones
  inmobiliarias, autenticación ni pantallas de producto.
- **FR-003**: La base visual MUST definir tipografía, tema, roles semánticos y
  componentes base mínimos y accesibles suficientes para construir interfaces
  posteriores sin fijar pantallas especulativas.
- **FR-004**: Cada ambiente MUST declarar explícitamente sus valores requeridos;
  el inicio MUST validar formato, presencia y restricciones de seguridad antes
  de aceptar tráfico.
- **FR-005**: El sistema MUST evitar valores inseguros por defecto y MUST impedir
  que secretos aparezcan en diagnósticos, logs o respuestas operativas.
- **FR-006**: El contrato de servicio MUST estar publicado y versionado, e
  incluir formatos de entrada, salida, errores y correlación.
- **FR-007**: Los cambios compatibles MUST conservar la versión principal del
  contrato; todo cambio incompatible MUST publicar una nueva versión principal
  o ser rechazado.
- **FR-008**: El consumidor web MUST derivar sus definiciones del contrato
  publicado, y la verificación MUST detectar cualquier divergencia.
- **FR-009**: Las solicitudes MUST aceptar o generar una identidad de
  correlación, devolverla al consumidor y propagarla a todo trabajo o efecto
  derivado.

#### Persistencia auditable

- **FR-010**: El runtime MUST verificar en cada ambiente la conectividad y las
  capacidades persistentes geográficas y vectoriales requeridas.
- **FR-011**: La evolución de estructuras persistentes MUST usar cambios
  ordenados y repetibles, incluir una versión inicial y detectar drift entre el
  estado declarado y el estado real.
- **FR-012**: Cada cambio persistente MUST declarar una ruta segura de reversión
  o compensación y MUST evitar estados parciales observables.
- **FR-013**: Los atributos persistentes comunes MUST representar identidad,
  creación, modificación, versión optimista, actor, origen y metadata de
  correlación sin acoplar las reglas internas a un mecanismo de almacenamiento.
- **FR-014**: Una actualización basada en una versión optimista obsoleta MUST
  rechazarse sin sobrescribir el cambio confirmado.

#### Trabajo durable y recuperación

- **FR-015**: Cada ejecución asíncrona MUST registrar una identidad idempotente
  compuesta por tipo de trabajo, objetivo lógico y clave idempotente, además de
  estado, timestamps, intentos, resultado resumido y error accionable cuando
  corresponda.
- **FR-016**: Repetir una ejecución con la misma identidad MUST producir como
  máximo un efecto lógico, incluso ante reinicios o fallos posteriores al
  efecto. Si la ejecución ya está en estado terminal, el runtime MUST devolver
  su estado y resultado registrados sin crear intentos ni efectos nuevos; una
  reejecución intencional MUST usar una clave nueva.
- **FR-017**: Los fallos transitorios MAY reintentarse hasta un límite explícito;
  los fallos permanentes o agotados MUST quedar en un estado terminal
  consultable y no reintentarse indefinidamente.
- **FR-018**: El runtime MUST permitir activaciones programadas simples y MUST
  impedir que ejecuciones superpuestas dupliquen efectos.
- **FR-019**: El almacenamiento de objetos MUST permitir escribir y recuperar
  versiones por identidad, preservando integridad, tipo de contenido y metadata
  de origen.
- **FR-020**: El contrato de almacenamiento MUST disponer de un reemplazo local
  para pruebas con el mismo comportamiento observable que el ambiente remoto.
- **FR-021**: La política de copia de seguridad y restauración MUST cubrir datos
  persistentes y objetos, identificar responsables, frecuencia, retención,
  procedimiento de verificación, RPO máximo de 24 horas y RTO máximo de 4
  horas.

#### Observabilidad y entrega

- **FR-022**: Los logs MUST ser estructurados y MUST correlacionar solicitudes,
  trabajos, objetos, cambios de datos y entregas usando por defecto sólo
  metadata permitida: correlación, operación, estado, duración, versión y tipo
  o estado del trabajo. Cuerpos, valores de headers, parámetros y atributos no
  permitidos MUST omitirse.
- **FR-023**: El runtime MUST registrar latencia, fallos y recorridos entre las
  superficies web, de servicio y de ejecución, aplicando filtrado uniforme de
  datos sensibles y la misma lista permitida de metadata en logs y trazas.
- **FR-024**: Cada superficie del runtime MUST publicar comprobaciones separadas
  de vida, readiness y versión; MUST declarar sus dependencias críticas, y su
  readiness MUST evaluarlas sin ejecutar efectos ni revelar secretos. Una falla
  MUST retirar sólo la superficie afectada y MUST mantener visible la
  degradación general.
- **FR-025**: La versión publicada MUST identificar de forma inequívoca el
  artefacto que está ejecutándose en cada ambiente.
- **FR-026**: El harness MUST verificar documentación, límites arquitectónicos,
  evolución y drift de datos, contratos compartidos, construcción de la
  superficie web y pruebas disponibles, y MUST bloquear una promoción ante un
  fallo requerido.
- **FR-027**: Una entrega MUST promover el mismo artefacto versionado por preview
  y producción, ejecutar cambios de datos de forma controlada y requerir un
  smoke test satisfactorio.
- **FR-028**: Cada entrega MUST disponer de un rollback documentado; si revertir
  datos no es seguro, MUST aplicar una compensación aprobada o detener la
  promoción.
- **FR-029**: Ejecuciones, cambios de datos, escrituras de objetos y entregas
  MUST conservar evidencia operativa suficiente para reconstruir actor,
  versión, tiempo, resultado y correlación.
- **FR-030**: El incremento MUST documentar inicio, configuración requerida,
  contratos, ejecución de checks, recuperación, promoción y rollback para que
  otra persona pueda repetirlos.
- **FR-031**: Hasta que exista identidad de producto, preview y producción MUST
  permanecer restringidos mediante controles del entorno; sólo la comprobación
  básica de vida MAY ser pública y su respuesta MUST omitir versión,
  dependencias y cualquier otro detalle interno.

### Key Entities

- **Runtime Version**: Identifica de forma inmutable el artefacto promovido y los
  ambientes donde se ejecuta.
- **Contract Version**: Representa una versión publicada de las entradas,
  salidas, errores y reglas de compatibilidad compartidas con sus consumidores.
- **Persistent Record Metadata**: Conjunto común de identidad, timestamps,
  versión optimista, actor, origen y correlación que acompaña datos auditables.
- **Schema Change**: Cambio ordenado del estado persistente, con versión,
  resultado y ruta de reversión o compensación.
- **Job Execution**: Ejecución idempotente cuya identidad combina tipo de
  trabajo, objetivo lógico y clave idempotente; conserva estado, timestamps,
  intentos, resultado y error resumido.
- **Stored Object Version**: Versión inmutable de contenido identificada por
  objeto, integridad, tipo, origen y tiempo de escritura.
- **Operational Signal**: Evento, log, métrica o tramo de recorrido asociado a
  una correlación. Por defecto contiene sólo operación, estado, duración,
  versión y tipo o estado del trabajo, y excluye cualquier atributo no
  permitido.
- **Recovery Policy**: Compromiso operativo que define alcance, responsables,
  frecuencia, retención, RPO, RTO y procedimiento verificable de restauración.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Iniciar una aplicación coherente | UM-H1-001 a UM-H1-006 |
| User Story 2 - Evolucionar datos con trazabilidad | UM-H1-007 a UM-H1-009 |
| User Story 3 - Ejecutar trabajo durable y recuperable | UM-H1-010 a UM-H1-012 |
| User Story 4 - Diagnosticar y promover una versión | UM-H1-016 a UM-H1-020 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H1-001 | FR-001 | US1.4, SC-003 |
| UM-H1-002 | FR-002 | US1.1, SC-001 |
| UM-H1-003 | FR-003 | US1.5 and the WCAG protocol |
| UM-H1-004 | FR-006, FR-007 | US1.3, SC-003 |
| UM-H1-005 | FR-008 | US1.3, SC-003 |
| UM-H1-006 | FR-004, FR-005 | US1.2, SC-002 |
| UM-H1-007 | FR-010 | US2.1, SC-006 |
| UM-H1-008 | FR-011, FR-012 | US2.1-US2.3, SC-003 |
| UM-H1-009 | FR-013, FR-014 | US2.4-US2.5 |
| UM-H1-010 | FR-015-FR-018 | US3.1-US3.3 and US3.6, SC-004 |
| UM-H1-011 | FR-019, FR-020 | US3.4, SC-005 |
| UM-H1-012 | FR-021 | US3.5, SC-009 |
| UM-H1-016 | FR-009, FR-022, FR-029 | US4.1, SC-007 |
| UM-H1-017 | FR-023 | US4.1 and US4.5, SC-007 and SC-010 |
| UM-H1-018 | FR-024, FR-025 | US4.2, SC-006 and SC-010 |
| UM-H1-019 | FR-026 | US1.3-US1.4, SC-001 and SC-003 |
| UM-H1-020 | FR-027-FR-031 | US4.3-US4.6, SC-008-SC-009 and SC-011 |

## Constitution Alignment *(mandatory)*

- **Persistent product objects**: Este incremento no crea búsquedas, listings,
  recomendaciones, feedback ni notificaciones. Establece primitives
  persistentes y evidencia operativa para que esos objetos futuros no dependan
  de chat, logs o memoria efímera.
- **Evidence and audit needs**: Versiones de runtime y contrato, cambios de
  datos, ejecuciones, objetos, promociones y reversiones conservan actor,
  timestamp, resultado y correlación suficientes para reconstruir el recorrido.
- **LLM boundary**: No se incorpora un LLM ni un orquestador agente en este
  incremento. Ninguna decisión de runtime, persistencia, reintento o promoción
  depende de generación.
- **Verification approach**: Checks automatizados de dependencias y contratos,
  evolución y drift, concurrencia optimista, idempotencia, almacenamiento,
  readiness, filtrado de datos sensibles, construcción, smoke test y rollback;
  ensayo documentado de restauración para la política de recuperación.
- **Dependency direction**: Las reglas internas no dependen de interfaz,
  persistencia, ejecución, observabilidad ni proveedores externos; los checks
  convierten esta restricción en una condición verificable.
- **Minimal change**: La base se limita a las capacidades necesarias para
  desbloquear los siguientes incrementos y excluye funciones de producto,
  identidad, dashboards y complejidad operativa no justificada.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona del equipo sin conocimiento previo de la preparación puede
  iniciar el runtime local y verificar sus superficies básicas en 15 minutos o
  menos siguiendo la documentación.
- **SC-002**: El 100% de los casos de prueba con configuración obligatoria
  faltante, mal formada o insegura impide operar y devuelve un diagnóstico
  accionable con cero secretos expuestos.
- **SC-003**: El harness detecta el 100% de los casos de prueba que introducen
  dependencias prohibidas, contratos incompatibles no versionados o drift
  persistente.
- **SC-004**: Diez repeticiones con el mismo tipo de trabajo, objetivo lógico y
  clave idempotente producen exactamente un efecto lógico y un único resultado
  final consultable; reutilizar la clave con otro tipo u objetivo produce una
  ejecución independiente, y repetir una identidad terminal crea cero intentos
  y efectos adicionales.
- **SC-005**: El 100% de los objetos del conjunto de prueba conserva integridad,
  tipo y versiones recuperables sin diferencias de contenido.
- **SC-006**: La pérdida simulada de una dependencia crítica cambia a no
  disponible el readiness de la superficie afectada en menos de 60 segundos,
  mantiene sin cambios las superficies sanas, hace visible la degradación
  general y genera cero efectos colaterales.
- **SC-007**: El 100% de las solicitudes y trabajos del recorrido de referencia
  puede reconstruirse mediante correlación usando sólo metadata permitida, con
  cero cuerpos, valores de headers, parámetros, secretos o atributos no
  permitidos en logs y trazas predeterminados.
- **SC-008**: Una versión candidata puede promoverse por preview y producción
  usando el mismo artefacto, superar su smoke test y restaurar la versión
  anterior en 15 minutos o menos.
- **SC-009**: La política de recuperación cubre el 100% de los datos persistentes
  y objetos declarados dentro del alcance, con RPO máximo de 24 horas, RTO
  máximo de 4 horas y un procedimiento de restauración verificable.
- **SC-010**: Una persona del equipo que no causó un fallo representativo puede
  identificar la superficie y ejecución afectadas mediante estado, logs y
  trazas en 15 minutos o menos.
- **SC-011**: El 100% de los intentos externos del conjunto de prueba contra
  preview y producción son rechazados, excepto la comprobación básica de vida,
  que expone cero detalles de versión, dependencias o configuración.

## Assumptions

- El alcance incluye exactamente UM-H1-001 a UM-H1-012 y UM-H1-016 a
  UM-H1-020.
- Identidad, invitaciones y roles (UM-H1-023 y UM-H1-013 a UM-H1-015),
  dashboard técnico (UM-H1-021) y threat model fundacional (UM-H1-022) se
  implementarán en incrementos posteriores.
- También quedan fuera datos inmobiliarios, imports, búsquedas, scoring,
  recomendaciones, agente conversacional, scraping y pantallas funcionales de
  producto.
- Los ambientes local, preview y producción y las credenciales necesarias
  estarán disponibles durante la implementación; sus diferencias se expresan
  mediante configuración, no mediante artefactos distintos.
- Las decisiones de tecnología ya aprobadas en la constitución y ADR vigente se
  aplicarán durante el plan; esta especificación define resultados observables
  sin reabrir esas decisiones.
- La cohorte privada todavía no está activa y ningún usuario final depende de
  este runtime antes del incremento de identidad. Hasta entonces, preview y
  producción permanecen restringidos mediante controles del entorno.
- El objetivo inicial de recuperación es RPO máximo de 24 horas y RTO máximo de
  4 horas. Alta disponibilidad, replicación avanzada y recuperación regional
  quedan fuera de este incremento.
- Los receptores remotos de telemetría pueden estar temporalmente
  indisponibles; esa falla debe ser visible pero no debe corromper estado ni
  revelar información sensible.
