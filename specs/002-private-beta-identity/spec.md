# Feature Specification: Private Beta Identity

**Feature Branch**: `002-private-beta-identity`

**Created**: 2026-07-29

**Status**: Ready for planning

**Input**: User description: "Implementar el incremento `private-beta-identity`
del backlog, con alcance exacto UM-H1-023 y UM-H1-013 a UM-H1-015."

## Clarifications

### Session 2026-07-29

- Q: ¿Debe usarse el nombre canónico del backlog y su alcance exacto? → A: Sí;
  el incremento es `private-beta-identity` e incluye UM-H1-023 y UM-H1-013 a
  UM-H1-015.
- Q: ¿La gestión completa de invitaciones forma parte de este incremento? → A:
  No. Crear, revocar, reenviar, administrar cupos y operar expiraciones queda
  en UM-H6-001. Este incremento recibe invitaciones precargadas mediante un
  mecanismo operativo controlado y auditable.
- Q: ¿Dónde viven la autenticación, la autorización y los datos de acceso? → A:
  Proveedores externos resuelven identidad y entrega de email detrás de límites
  reemplazables; Umbral conserva invitaciones, usuarios de producto, roles,
  ownership y auditoría como fuente de verdad.
- Q: Después del primer acceso exitoso, ¿qué debe autorizar los siguientes magic
  links de esa persona? → A: La invitación pasa a `accepted`; los accesos
  posteriores dependen del usuario de producto activo.
- Q: ¿Qué rol debe recibir una persona al completar por primera vez su
  activación? → A: Toda activación asigna `user`; los roles `operator` y
  `administrator` sólo se conceden después mediante una operación administrativa
  separada y auditable.
- Q: ¿Cuánto tiempo debe permanecer válida una sesión antes de exigir un nuevo
  magic link? → A: La sesión vence sólo después de siete días consecutivos sin
  actividad; cada operación protegida válida reinicia ese período.
- Q: Si una persona solicita un nuevo magic link antes de que venza el anterior,
  ¿qué debe ocurrir con los enlaces previos no usados? → A: Sólo el enlace más
  reciente permanece válido; emitirlo invalida todos los anteriores no usados.
- Q: ¿Qué límite debe aplicarse a las solicitudes de magic link para reducir
  abuso? → A: Hasta tres solicitudes por email normalizado y veinte por origen
  de solicitud en cada ventana móvil de 15 minutos.

## Operational Definitions

- **Email normalizado**: representación canónica usada para comparar y buscar
  invitaciones y usuarios. La regla exacta debe estar documentada, ser estable
  y aplicarse igual al precargar, solicitar acceso y vincular identidad. No se
  asume que dos direcciones distintas pertenecen a la misma persona.
- **Persona invitada**: dirección de email normalizada que posee una invitación
  activa precargada. La invitación habilita únicamente la activación inicial y
  pasa a `accepted` al completarla; desde entonces, el estado del usuario de
  producto gobierna accesos posteriores. La invitación no concede por sí sola
  un rol privilegiado.
- **Magic link válido**: enlace destinado a Umbral, emitido para una persona
  invitada o un usuario activo, no alterado, no vencido, todavía no consumido y
  no reemplazado por una emisión posterior. Su vigencia máxima es de 15 minutos.
- **Usuario de producto**: identidad interna y estable que posee recursos de
  Umbral. Accesos sucesivos con la misma identidad válida deben resolver al
  mismo usuario.
- **Identidad externa**: prueba de autenticación emitida por el proveedor y
  validada por Umbral. Se vincula mediante el identificador estable del
  proveedor; el email informado no basta para fusionar identidades.
- **Ownership**: relación explícita entre un usuario y un recurso de producto.
  Ningún rol implica acceso a recursos ajenos si ese permiso no está definido
  expresamente.
- **Operación protegida**: cualquier lectura, creación, cambio o efecto que no
  sea público. Cada operación protegida debe tener una regla explícita de rol,
  ownership y estado de usuario; la ausencia o ambigüedad de una regla deniega
  el acceso.
- **Resultado parcial de acceso**: invitación, usuario, vínculo, sesión o rol
  creado de forma observable aunque el recorrido no haya terminado de manera
  válida. Los fallos de proveedor no pueden dejar resultados parciales.
- **Actividad de sesión**: operación protegida válida realizada por el usuario.
  La sesión vence al completar siete días consecutivos sin esa actividad; no
  posee un vencimiento absoluto mientras continúe en uso.
- **Origen de solicitud**: señal minimizada que permite agrupar solicitudes
  provenientes del mismo origen para aplicar controles de abuso sin conservar
  más datos personales que los autorizados por la política vigente.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Acceder a la beta por invitación (Priority: P1)

Como persona invitada, quiero solicitar un magic link y entrar sin contraseña,
para usar Umbral mediante un acceso simple que no permita el registro abierto.

**Why this priority**: La puerta de salida de H1 requiere que un usuario
invitado pueda autenticarse contra una aplicación desplegada. Sin este
recorrido no existe una beta privada demostrable.

**Independent Test**: Con una invitación precargada y proveedores disponibles,
una persona solicita acceso, consume un enlace válido, llega a una superficie
protegida y repite el acceso conservando el mismo usuario de producto. Emails
no invitados y enlaces inválidos no obtienen acceso.

**Acceptance Scenarios**:

1. **Given** una invitación activa para un email normalizado, **When** la persona
   solicita acceso y consume dentro de 15 minutos el enlace recibido, **Then**
   obtiene una sesión vinculada a un único usuario de producto con rol `user` y
   la invitación pasa a `accepted`.
2. **Given** un usuario activo ya vinculado y su invitación aceptada, **When**
   vuelve a acceder mediante una nueva prueba válida de la misma identidad
   externa, **Then** ingresa como el mismo usuario sin requerir otra invitación
   ni duplicar usuario o vínculo.
3. **Given** un email sin invitación activa, **When** solicita acceso, **Then**
   no se envía un enlace que conceda acceso y la respuesta visible no revela si
   el email pertenece a la cohorte.
4. **Given** un enlace vencido, consumido, alterado o destinado a una ubicación
   no aprobada, o un enlace anterior reemplazado por otro más reciente, **When**
   alguien intenta usarlo, **Then** no obtiene sesión, recibe una recuperación
   segura y puede iniciar una solicitud nueva.
5. **Given** una identidad válida cuyo email o identificador estable entra en
   conflicto con un vínculo existente, **When** intenta acceder, **Then** el
   acceso se rechaza sin fusionar cuentas y el conflicto queda disponible para
   revisión controlada.
6. **Given** un usuario deshabilitado, **When** presenta una prueba de identidad
   válida, **Then** no obtiene acceso a operaciones protegidas.
7. **Given** una sesión activa, **When** el usuario cierra sesión, **Then** esa
   sesión deja de habilitar operaciones protegidas.
8. **Given** una sesión sin siete días consecutivos de inactividad, **When** el
   usuario ejecuta una operación protegida válida, **Then** la sesión continúa
   y el período de inactividad comienza nuevamente.
9. **Given** una sesión que completa siete días consecutivos sin actividad,
   **When** intenta la siguiente operación protegida, **Then** se exige un nuevo
   magic link antes de continuar.
10. **Given** tres solicitudes para el mismo email normalizado o veinte para el
    mismo origen dentro de 15 minutos, **When** llega otra solicitud en esa
    ventana, **Then** se conserva la respuesta neutral, no se emite otro enlace
    y no se invalida el enlace válido más reciente.

---

### User Story 2 - Mantener aislados usuarios y responsabilidades (Priority: P2)

Como participante de la beta, quiero que cada operación compruebe mi identidad,
rol y ownership, para que ninguna persona pueda ver o cambiar recursos ajenos
por manipular una referencia o poseer un rol amplio.

**Why this priority**: El aislamiento por usuario es una condición de confianza
para persistir búsquedas, preferencias, conversaciones y recomendaciones, y
desbloquea incrementos posteriores sin depender de controles implícitos.

**Independent Test**: Una matriz finita cruza persona anónima, usuario,
operador, administrador y usuario deshabilitado con recursos propios, ajenos y
operativos. Sólo pasan las combinaciones expresamente permitidas.

**Acceptance Scenarios**:

1. **Given** un usuario activo y un recurso propio, **When** ejecuta una
   operación permitida para usuarios, **Then** la operación continúa.
2. **Given** un usuario activo y un recurso ajeno, **When** intenta leerlo o
   modificarlo, **Then** la operación se deniega sin revelar contenido ni
   confirmar más información que la necesaria.
3. **Given** un operador, **When** ejecuta una acción operativa expresamente
   asignada, **Then** la acción continúa y queda auditada.
4. **Given** un operador o administrador sin permiso explícito sobre contenido
   privado de un usuario, **When** intenta acceder a ese contenido, **Then** el
   acceso se deniega.
5. **Given** un rol desconocido, una regla ausente o ownership ambiguo, **When**
   se evalúa una operación protegida, **Then** se aplica deny-by-default.
6. **Given** un usuario cuyo estado fue deshabilitado o cuyo rol fue retirado,
   **When** intenta la siguiente operación protegida, **Then** el cambio ya está
   vigente aunque posea una sesión creada con anterioridad.

---

### User Story 3 - Elegir y operar proveedores reemplazables (Priority: P3)

Como responsable de la plataforma, quiero seleccionar proveedores de identidad
y email con criterios explícitos y mantener las decisiones de acceso en
Umbral, para operar la beta sin aceptar riesgos ocultos ni quedar atrapado en
un proveedor.

**Why this priority**: La selección habilita el recorrido de acceso, pero debe
resolverse sin trasladar roles, ownership o auditoría fuera del producto.

**Independent Test**: Un registro de decisión compara candidatos contra todos
los criterios obligatorios, define responsables y ambientes, y una simulación
de indisponibilidad demuestra que ninguno concede acceso ni deja resultados
parciales.

**Acceptance Scenarios**:

1. **Given** al menos dos alternativas viables por capacidad, **When** se toma
   la decisión, **Then** quedan comparadas autenticación por magic link,
   invalidación de enlaces anteriores, validación independiente, aislamiento de
   datos, entregabilidad, costo, observabilidad, soporte local y estrategia de
   salida.
2. **Given** proveedores seleccionados, **When** se habilita un ambiente,
   **Then** sus credenciales, destinos y datos están aislados de los demás
   ambientes y tienen responsables identificados.
3. **Given** una indisponibilidad o rechazo del proveedor de identidad, **When**
   una persona intenta acceder, **Then** no obtiene sesión ni se crea o modifica
   un vínculo de identidad.
4. **Given** una indisponibilidad o rechazo del proveedor de email, **When** se
   solicita acceso, **Then** no se concede acceso, el fallo queda visible para
   operación y la respuesta pública conserva el mismo acuse neutral que para
   cualquier email, con una forma segura de volver a intentar.
5. **Given** la necesidad de sustituir un proveedor, **When** se revisa la
   estrategia de salida, **Then** usuarios, roles, ownership e historial
   auditable permanecen bajo control de Umbral.

---

### User Story 4 - Reconstruir decisiones de acceso (Priority: P4)

Como responsable de seguridad u operación, quiero reconstruir solicitudes,
accesos y denegaciones mediante evidencia mínima y correlacionada, para
investigar incidentes sin exponer tokens ni datos personales innecesarios.

**Why this priority**: Una beta privada necesita detectar abuso y explicar
decisiones de acceso, pero la propia observabilidad no debe ampliar la
exposición de información sensible.

**Independent Test**: Se recorren los eventos de todos los escenarios de
autenticación y autorización, se reconstruye cada resultado mediante
referencias internas, razón y correlación, y se comprueba que no aparecen
tokens, enlaces completos, credenciales o cuerpos sensibles.

**Acceptance Scenarios**:

1. **Given** una solicitud, emisión conocida, consumo, expiración, reutilización,
   rechazo o cierre de sesión, **When** se revisa la auditoría, **Then** existe
   un evento con tipo, resultado, razón, momento y correlación.
2. **Given** una operación protegida permitida o denegada, **When** se revisa la
   auditoría, **Then** puede identificarse actor interno, regla evaluada y
   resultado sin copiar el contenido del recurso.
3. **Given** cualquier evento o diagnóstico del recorrido, **When** se
   inspeccionan sus campos, **Then** no contiene tokens, enlaces completos,
   credenciales, cuerpos de mensajes ni PII que no sea necesaria para el fin
   auditado.

### Edge Cases

- Emitir un nuevo magic link invalida todos los enlaces anteriores no usados
  para esa identidad de acceso; una confirmación demorada de una emisión
  anterior no puede reactivarlos.
- Solicitudes simultáneas alcanzan el límite en distinto orden: como máximo tres
  por email normalizado y veinte por origen pueden iniciar una emisión dentro de
  la misma ventana móvil de 15 minutos.
- Una solicitud excede el límite mientras existe un enlace válido: no inicia una
  emisión nueva ni invalida el enlace existente; una vez fuera de la ventana
  puede volver a intentarse.
- Diez entregas o confirmaciones duplicadas del proveedor para el mismo intento
  producen como máximo un consumo válido, un usuario y un vínculo.
- Variaciones de mayúsculas, espacios o representación cubiertas por la regla
  de normalización resuelven a la misma invitación; transformaciones no
  declaradas no fusionan direcciones.
- Un proveedor confirma identidad pero omite un atributo requerido o devuelve
  uno no verificado: Umbral rechaza el acceso y no crea el vínculo.
- El proveedor reasigna un email a otro identificador estable: Umbral no
  reemplaza ni fusiona el vínculo existente de forma automática.
- Una invitación precargada cambia de estado durante una solicitud: la
  elegibilidad se vuelve a comprobar antes de crear la sesión.
- El estado o rol del usuario cambia durante una sesión: la siguiente operación
  protegida usa el estado vigente.
- Una operación llega en el límite de siete días sin actividad: una única
  autoridad temporal decide si la sesión ya venció antes de admitir la
  operación; una sesión vencida no puede reactivarse mediante esa solicitud.
- Una operación protegida recibe una referencia inexistente o ajena: la
  respuesta no debe permitir distinguir ambos casos cuando esa diferencia
  revelaría existencia de datos.
- El reloj del consumidor y el del emisor difieren: la decisión de expiración
  usa una autoridad temporal coherente y no extiende la vigencia aprobada.
- El evento de auditoría no puede persistirse: la operación sensible no se
  considera completada de forma silenciosa; se aplica la política segura
  definida para ese tipo de evento.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Antes de habilitar acceso fuera de pruebas controladas, el proyecto
  MUST registrar la selección de proveedores de identidad y email.
- **FR-002**: La selección MUST comparar magic link, validación independiente
  por Umbral, invalidación de enlaces anteriores, aislamiento de datos,
  entregabilidad, costo, observabilidad, soporte local y estrategia de salida;
  riesgos aceptados MUST indicar razón, responsable y mitigación.
- **FR-003**: La selección MUST definir para cada ambiente el proveedor
  habilitado, el responsable de sus credenciales y datos, los destinos
  permitidos y el procedimiento para deshabilitarlo o sustituirlo.
- **FR-004**: Umbral MUST conservar como fuente de verdad las invitaciones,
  usuarios de producto, estados de acceso, roles, ownership y eventos de
  auditoría; los proveedores MUST NOT decidir autorización de producto.
- **FR-005**: Sólo un email normalizado con invitación activa MAY iniciar la
  activación inicial; después de completarla, sólo un usuario de producto activo
  y ya vinculado MAY iniciar accesos posteriores.
- **FR-006**: Solicitudes para emails invitados y no invitados MUST producir la
  misma respuesta pública, sin confirmar membresía de la cohorte ni el resultado
  individual de entrega.
- **FR-007**: Cada magic link MUST expirar como máximo 15 minutos después de su
  emisión, admitir un solo consumo válido y conducir únicamente a destinos
  aprobados de Umbral. Emitir uno nuevo MUST invalidar todos los anteriores no
  usados para la misma identidad de acceso.
- **FR-008**: Una invitación MUST poder precargarse mediante una operación
  controlada que identifique al actor, origen, email normalizado, estado y
  momento, sin requerir la consola de gestión prevista para UM-H6-001.
- **FR-009**: Antes de crear una sesión, aunque el proveedor ya haya autenticado
  la identidad, Umbral MUST comprobar una invitación activa durante la
  activación inicial o el estado activo del usuario en accesos posteriores.
- **FR-010**: Al completar la activación inicial, Umbral MUST cambiar la
  invitación a `accepted` de forma atómica con la creación o vinculación del
  usuario y la asignación del rol `user`; un fallo MUST conservar la invitación
  activa y no dejar un usuario, vínculo o rol parcial.
- **FR-011**: El primer acceso válido MUST crear o vincular exactamente un
  usuario de producto y accesos posteriores de la misma identidad MUST resolver
  al mismo usuario.
- **FR-012**: El vínculo externo MUST usar el identificador estable y único del
  proveedor; coincidencias de email por sí solas MUST NOT fusionar usuarios o
  sustituir vínculos existentes.
- **FR-013**: Conflictos entre invitación, email verificado, usuario e identidad
  externa MUST denegarse sin cambios parciales y quedar disponibles para
  revisión controlada.
- **FR-014**: Toda operación protegida MUST validar una identidad vigente, el
  estado activo del usuario, un permiso explícito del rol y el ownership cuando
  corresponda.
- **FR-015**: El rol `user` MUST limitarse a operaciones de producto permitidas
  sobre recursos propios y MUST ser el único rol asignado automáticamente
  durante la activación inicial.
- **FR-016**: El rol `operator` MUST limitarse a operaciones expresamente
  definidas y MUST NOT conceder acceso implícito al contenido privado de
  usuarios.
- **FR-017**: El rol `administrator` MUST permitir administrar asignaciones
  sensibles de acceso y roles mediante operaciones controladas, pero MUST NOT
  conceder acceso implícito al contenido privado de usuarios. Los roles
  `operator` y `administrator` MUST concederse sólo después de la activación,
  mediante una operación administrativa separada y auditable.
- **FR-018**: Una operación sin regla explícita, con rol desconocido o con
  ownership ausente o ambiguo MUST ser denegada por defecto.
- **FR-019**: Deshabilitar un usuario o retirar un rol MUST afectar la siguiente
  operación protegida aunque exista una sesión previa.
- **FR-020**: El usuario MUST poder cerrar su sesión; una sesión cerrada MUST
  dejar de habilitar operaciones protegidas.
- **FR-021**: Una sesión MUST vencer al completar siete días consecutivos sin
  actividad; cada operación protegida válida MUST reiniciar ese período y no se
  aplica un vencimiento absoluto mientras la sesión continúe en uso.
- **FR-022**: Fallos o rechazos de proveedores MUST NOT crear sesiones,
  usuarios, vínculos, roles ni resultados parciales que concedan acceso.
- **FR-023**: Los datos, credenciales y destinos de identidad y email MUST estar
  aislados por ambiente; un ambiente MUST NOT aceptar credenciales ni
  confirmaciones de proveedor pertenecientes a otro.
- **FR-024**: Umbral MUST registrar eventos auditables para precarga de
  invitación, solicitud de acceso, resultado conocido de entrega, consumo,
  expiración, reutilización, conflicto, creación o vínculo de usuario, inicio y
  cierre de sesión, cambio de estado o rol, y autorización permitida o denegada.
- **FR-025**: Cada evento de acceso MUST incluir tipo versionado, resultado,
  razón estable, referencias internas, ambiente, momento y correlación
  suficientes para reconstruir la decisión.
- **FR-026**: Eventos, diagnósticos y respuestas MUST NOT contener tokens,
  enlaces completos, credenciales, cuerpos de mensajes ni PII innecesaria.
- **FR-027**: Solicitudes y confirmaciones repetidas del proveedor MUST ser
  seguras ante duplicación: diez repeticiones del mismo caso MUST conservar como
  máximo un consumo válido, un usuario, un vínculo y una sesión resultante.
- **FR-028**: Los errores visibles al consumir un enlace o ejecutar una operación
  protegida MUST distinguir una recuperación posible de una denegación
  definitiva sin revelar existencia de invitaciones, usuarios, recursos,
  credenciales ni detalles internos del proveedor.
- **FR-029**: Umbral MUST permitir como máximo tres solicitudes de magic link
  por email normalizado y veinte por origen de solicitud dentro de cada ventana
  móvil de 15 minutos, contando solicitudes invitadas y no invitadas sin
  distinguirlas en la respuesta pública.
- **FR-030**: Una solicitud que exceda cualquiera de los límites MUST NOT iniciar
  una emisión, enviar email ni invalidar el enlace válido más reciente; MUST
  conservar la respuesta neutral y registrar la decisión sin datos personales
  innecesarios.

### Scope Boundaries

**Included**:

- Selección documentada de proveedores de identidad y email.
- Precarga controlada y auditable de invitaciones para habilitar el incremento.
- Solicitud y consumo de magic links para emails invitados.
- Mapeo estable entre identidad externa y usuario de producto.
- Roles mínimos `user`, `operator` y `administrator`.
- Autorización local deny-by-default con aislamiento por ownership.
- Cierre de sesión, estado de acceso y auditoría de autenticación y
  autorización.
- Comportamiento seguro ante duplicados, conflictos y fallos de proveedores.

**Excluded**:

- Registro abierto, contraseñas, proveedores sociales y autenticación
  multifactor.
- Consola de invitaciones con creación, revocación, reenvío, cupos y operación
  de expiraciones; corresponde a UM-H6-001.
- Onboarding de producto, términos, consentimiento y gestión autoservicio de
  cuenta.
- Recuperación o fusión automática de cuentas y cambio autoservicio de email.
- Vista de soporte, acceso excepcional a contenido privado y su flujo de
  aprobación.
- Gestión de permisos configurable por usuarios o roles adicionales.
- Notificaciones de producto; el email de autenticación no introduce el sistema
  de alertas del radar.

### Key Entities

- **Invitation**: elegibilidad precargada para un email normalizado; conserva
  identificador estable, estado `active` o `accepted`, origen, actor responsable
  y timestamps. Se relaciona como máximo con un usuario de producto y pasa a
  `accepted` al completar atómicamente la activación inicial.
- **Product User**: identidad interna estable; conserva email normalizado,
  estado de acceso y timestamps. Posee recursos de producto y puede tener una o
  más asignaciones de rol explícitas.
- **External Identity Link**: relación única entre proveedor, identificador
  externo estable y usuario de producto; conserva email verificado observado y
  momento de vinculación sin convertir el email en clave de fusión.
- **Role Assignment**: concesión vigente o retirada de uno de los roles mínimos
  a un usuario; conserva quién realizó el cambio, cuándo y su razón. La
  activación inicial crea únicamente la asignación `user`; cualquier rol
  privilegiado requiere una operación administrativa posterior.
- **Access Audit Event**: evidencia inmutable de una acción o decisión de
  autenticación o autorización; conserva referencias internas, tipo, resultado,
  razón, ambiente, timestamp y correlación bajo una política de datos mínimos.
- **Provider Decision Record**: decisión versionada que compara alternativas,
  registra selección, riesgos, responsables, límites por ambiente y estrategia
  de salida.

## Constitution Alignment *(mandatory)*

- **Persistent product objects**: invitación, usuario de producto, vínculo de
  identidad, asignación de rol y evento de acceso son objetos persistentes.
  Sesiones externas no sustituyen esos objetos ni se vuelven fuente de verdad
  de producto.
- **Evidence and audit needs**: cada cambio sensible y cada decisión de acceso
  registra evidencia mínima, razón estable, correlación y actor interno cuando
  exista. Conflictos y denegaciones permanecen reconstruibles sin copiar
  contenido privado.
- **LLM boundary**: N/A. Ninguna parte de autenticación, vinculación,
  autorización, roles o auditoría depende de interpretación generativa.
- **Verification approach**: escenarios de aceptación automatizados, matriz de
  autorización, pruebas de duplicación y conflicto, simulaciones de fallos,
  inspección de eventos y revisión del registro de decisión de proveedores.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: En al menos 20 recorridos representativos de beta, 95% de las
  personas invitadas completa su primer acceso en menos de tres minutos desde
  la solicitud hasta una superficie protegida.
- **SC-002**: El 100% del conjunto declarado de emails no invitados, usuarios
  deshabilitados y enlaces vencidos, reutilizados, reemplazados, alterados o con
  destino no permitido es rechazado sin revelar membresía de la cohorte.
- **SC-003**: El 100% de la matriz declarada de identidad, estado, rol,
  ownership y operación cumple los permisos explícitos y deny-by-default, con
  cero accesos cruzados entre usuarios.
- **SC-004**: Diez repeticiones de cada solicitud y confirmación duplicada del
  proveedor producen como máximo un consumo válido, un usuario, un vínculo y
  una sesión resultante.
- **SC-005**: El 100% de los eventos críticos declarados puede correlacionarse
  con su resultado y razón; cero eventos o diagnósticos contienen tokens,
  enlaces completos o credenciales.
- **SC-006**: En el 100% de las simulaciones declaradas de indisponibilidad,
  falta de respuesta y rechazo de identidad o email se crean cero sesiones,
  vínculos o usuarios parciales que concedan acceso.
- **SC-007**: El registro de decisión cubre el 100% de los criterios de
  UM-H1-023 y todo riesgo no resuelto posee aceptación explícita, responsable,
  mitigación y estrategia de salida.
- **SC-008**: El 100% de accesos válidos repetidos para una identidad ya
  vinculada resuelve al mismo usuario de producto, sin duplicados ni fusión
  automática de identidades conflictivas.
- **SC-009**: El 100% de sesiones con actividad protegida dentro de cada período
  de siete días permanece válido, y el 100% de sesiones que completa siete días
  consecutivos sin actividad exige un nuevo magic link.
- **SC-010**: En el 100% de las pruebas de límite, la cuarta solicitud por email
  normalizado y la vigésima primera por origen dentro de 15 minutos generan cero
  emisiones e invalidaciones, conservan una respuesta neutral y vuelven a
  admitir una solicitud al salir de la ventana.

## Assumptions

- `foundation-runtime` provee configuración por ambiente, persistencia,
  correlación, auditoría básica y superficies desplegables necesarias para
  demostrar este incremento.
- Las invitaciones de desarrollo, prueba y beta temprana se precargan mediante
  una operación interna controlada; su experiencia operativa completa se
  especificará en UM-H6-001.
- La vigencia máxima de 15 minutos del magic link es el valor seguro inicial.
  Cambiarla requiere evidencia y una actualización explícita de la
  especificación.
- Cada persona de la beta usa inicialmente un solo email invitado. Los hogares,
  cuentas compartidas y múltiples identidades vinculadas no forman parte de
  este incremento.
- El mapa de datos personales y las políticas de retención aplicables existen
  antes de usar datos de personas reales; este incremento conserva sólo la
  información mínima necesaria para identidad, autorización y auditoría.
- La actividad que reinicia el período de sesión es únicamente una operación
  protegida válida; solicitudes públicas, errores y operaciones denegadas no
  extienden la sesión.
- La señal de origen usada para limitar abuso se define durante la planificación
  bajo la política de datos personales, pero debe agrupar solicitudes de forma
  estable durante 15 minutos sin convertirse en identidad de usuario.
- Los permisos de recursos que todavía no existen se validan mediante una
  matriz y recursos representativos; cada incremento posterior debe extender
  esa matriz al introducir nuevas operaciones protegidas.
- La administración de roles durante este incremento se realiza mediante una
  operación controlada y auditable, sin construir una consola de producto.
