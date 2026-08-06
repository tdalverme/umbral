# Feature Specification: Structured Search Radar

**Feature Branch**: `004-structured-search-radar`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "Arranquemos con la especificacion del hito H2.3 - Busqueda, matching baseline y radar del backlog, con alcance exacto UM-H2-019 a UM-H2-034."

## Clarifications

### Session 2026-08-06

- Q: ¿La generacion de matches (el run) se ejecuta de forma sincronica al crear
  o editar el radar, o corre de forma asincronica como un job que publica
  resultados cuando termina? → A: Asincronica: el run se persiste y ejecuta
  como job, el radar muestra un estado "generando resultados" mientras corre y
  publica los matches al completarse; un run fallido conserva el ultimo run
  valido como unico resultado visible.
- Q: ¿El rol operador tiene en este incremento una superficie para ver u operar
  radares de usuarios, o la verificacion se hace con un actor de prueba y el
  operador queda sin acceso a radares de usuarios? → A: Sin superficie: el
  recorrido E2E y las verificaciones usan un actor de prueba del harness; el
  rol operador no accede a radares de usuarios en este incremento (la consola
  operativa es H6).
- Q: ¿Las contribuciones del scoring se muestran en la interfaz del radar en
  este incremento o solo se persisten y exponen por API? → A: Desglose simple
  en el detalle del match: el detalle muestra la contribucion de cada dimension
  del fit objetivo sin presentarse como certeza; las cards y la lista muestran
  solo el score total. La explicacion con evidencia y riesgos es H3.
- Q: ¿Cual es el tiempo maximo aceptable entre disparar un run y ver los
  matches publicados en el radar? → A: Menos de 30 segundos: los runs sobre el
  conjunto de prueba publican sus matches en menos de 30 segundos desde que se
  disparan, con el estado "generando resultados" visible mientras tanto.

Las decisiones por default (politica inicial, scoring baseline simple, pausar
vs archivar, contrato minimo de eventos) estan documentadas en
[Assumptions](#assumptions).

## Operational Definitions

- **Radar (search profile)**: busqueda persistente del usuario con nombre,
  operacion (alquiler), zonas de CABA, presupuesto, ambientes, superficie,
  estado y politica inicial. Es la fuente de verdad de la intencion de busqueda;
  nada relevante vive solo en el chat.
- **Estado del radar**: activo, pausado o archivado. Pausar detiene la
  generacion de nuevos runs; archivar oculta la busqueda del selector
  conservando todos sus datos e historial.
- **Politica inicial**: conjunto versionado de reglas que define, para cada hard
  filter, como tratar valores desconocidos del listing, y las reglas de
  confirmacion al crear o editar el radar.
- **Version del radar (snapshot)**: imagen inmutable del perfil que un
  recommendation run congela como input; una edicion crea una version nueva sin
  modificar las anteriores.
- **Hard filter**: condicion binaria y determinista (presupuesto, operacion,
  ubicacion, ambientes y requisitos obligatorios) que decide si un listing
  entra o no al candidate set, sin embeddings ni modelos.
- **Valor desconocido**: dato ausente, ambiguo o fuera de rango de un listing;
  cada filtro declara explicitamente como tratarlo y esa politica queda
  versionada con el perfil.
- **Scoring baseline**: ordenamiento determinista y versionado de los
  candidatos por fit objetivo (presupuesto, zonas, ambientes, superficie), con
  tie-break estable y contribuciones visibles por dimension. No es el scoring
  completo de H3.
- **Recommendation run**: ejecucion persistida y asincronica (job) que congela
  profile snapshot, candidate set, version de scoring y tiempos, y produce
  items ordenados; mientras corre, el radar muestra "generando resultados"; un
  run fallido no reemplaza el ultimo run valido.
- **Recommendation item (match)**: par listing-run con score, posicion,
  contribuciones y referencia al run persistido; es la unidad que el usuario
  explora en lista, mapa y detalle.
- **Precision geografica autorizada**: precision declarada por la
  normalizacion Silver (exact/block/barrio/aproximada/desconocida); ninguna
  superficie puede revelar coordenadas mas precisas que esa precision.
- **Lineage permitido**: para cada match se puede volver al listing Silver, al
  snapshot Bronze y a la version de parser que lo produjo, sin pasos no
  registrados.
- **Estado de pantalla**: loading, empty, parcial, error recuperable, no
  autorizado y no encontrado; cada superficie distingue esos estados en desktop
  y mobile.
- **Evento de producto**: registro versionado de una accion de activacion o
  exploracion (crear radar, run publicado, impresion, vista de detalle, apertura
  de fuente) sin PII innecesaria, de acuerdo con el diccionario de eventos.
- **Recorrido E2E inicial**: un lote con registros validos e invalidos produce
  reporte, entidades Silver, radar y detalles correctos, y reimportar el mismo
  lote no duplica nada.

## Review and Measurement Protocol

- La puerta de salida del hito: un operador importa propiedades (H2.1/H2.2) y un
  usuario crea una busqueda, ejecuta hard filters y revisa matches persistentes
  de punta a punta. Este incremento entrega el radar completo de lista, mapa y
  detalle; la explicacion con evidencia (H3), el feedback (H3), el chat (H4) y
  las alertas (H5) NO se evaluan aqui.
- El conjunto de prueba del harness reutiliza la fixture Silver de referencia
  (H2.2) e incorpora radares con casos golden de hard filters, incluidos
  valores desconocidos, presupuestos sin techo, zonas sin geometria y cambios
  de perfil.
- Los hard filters se verifican comparando el resultado contra el caso golden
  declarado: entrada, politica de desconocido y resultado esperado.
- El determinismo del scoring se verifica ejecutando dos veces el mismo perfil
  sobre el mismo candidate set y comparando orden, scores y desglose.
- La persistencia de runs se verifica induciendo un fallo de publicacion y
  confirmando que el ultimo run valido sigue visible sin resultados parciales.
- La precision geografica se verifica comparando la precision autorizada de cada
  listing con el punto renderizado; ningun caso puede excederla.
- Los estados de pantalla y la accesibilidad se verifican con un recorrido de
  interfaz automatizado en desktop y mobile que cubre cada estado (loading,
  empty, parcial, error, no autorizado, no encontrado) y navegacion por teclado.
- La instrumentacion se verifica confirmando que cada accion declarada emite su
  evento con version y sin PII innecesaria.
- El E2E se verifica recorriendo lote a reporte, Silver, radar y detalle con el
  actor de prueba del harness, y reimportando el mismo lote para confirmar 0
  duplicados de listings ni matches.
- El tiempo de publicacion de los runs se verifica midiendo desde que se dispara
  el run hasta que los matches quedan visibles; objetivo: menos de 30 segundos
  sobre el conjunto de prueba.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Crear un radar estructurado (Priority: P1)

Como usuario invitado, quiero definir como quiero vivir (presupuesto, zonas y
requisitos P0) mediante un formulario guiado y confirmar antes de que quede
activo, para que el sistema empiece a buscar por mi sin que yo tenga que saber
de filtros.

**Why this priority**: Sin un radar persistente no hay candidatos ni matches; es
la base de todo el hito y la metrica de activacion de beta (>= 70% de usuarios
con radar y cinco evaluaciones).

**Independent Test**: El conjunto de prueba produce radares persistentes con
nombre, operacion, zonas, presupuesto, ambientes, superficie, estado y politica
inicial; cada edicion crea una version nueva; la creacion emite su evento.

**Acceptance Scenarios**:

1. **Given** un usuario invitado autenticado, **When** completa presupuesto,
   zonas y requisitos P0 y confirma el resumen, **Then** se crea un radar activo
   con estado y politica inicial, queda en el selector y se emite el evento de
   crear radar.
2. **Given** el usuario intenta confirmar sin datos obligatorios (por ejemplo,
   sin ninguna zona), **When** confirma, **Then** se muestran errores
   accionables y no se persiste ningun dato parcial.
3. **Given** el usuario edita un radar existente y confirma, **When** se guarda,
   **Then** se crea una version nueva del perfil y la anterior queda intacta.
4. **Given** el onboarding presenta un resumen antes de confirmar, **When** el
   usuario lo revisa, **Then** el resumen refleja exactamente lo que se
   persistira, sin datos ocultos.
5. **Given** un radar con valores desconocidos en algun criterio, **When** se
   crea o edita, **Then** la politica inicial declara explicitamente como se
   trataran esos desconocidos y queda versionada con el perfil.

---

### User Story 2 - Administrar las busquedas sin mezclar datos (Priority: P1)

Como usuario con mas de un radar, quiero ver, seleccionar, editar, pausar y
archivar mis busquedas manteniendo el contexto, para que cada radar sea
independiente y nunca vea datos de otro.

**Why this priority**: El selector y la administracion son la base del contexto
multi-radar; mezclar datos entre radares violaria el aislamiento por usuario y
la confianza de beta.

**Independent Test**: El conjunto de prueba recorre crear, listar, obtener,
editar, pausar, reanudar y archivar sobre varios radares del mismo usuario, y
verifica rechazo deny-by-default sobre radares ajenos.

**Acceptance Scenarios**:

1. **Given** un usuario con radares activos, pausados y archivados, **When**
   abre el selector, **Then** distingue los tres estados y mantiene el contexto
   del radar seleccionado en desktop y mobile.
2. **Given** un radar activo, **When** el usuario lo pausa, **Then** deja de
   generar nuevos runs, los resultados vigentes permanecen visibles y al
   reanudar puede volver a correr.
3. **Given** un radar archivado, **When** el usuario lo archiva, **Then**
   desaparece del selector por defecto pero sus datos e historial se conservan.
4. **Given** un usuario intenta operar un radar que no le pertenece, **When**
   crea, edita, pausa o archiva, **Then** la accion se rechaza sin revelar
   datos del radar ajeno.
5. **Given** dos usuarios editan el mismo radar de forma concurrente, **When**
   uno de ellos guarda, **Then** el otro recibe un error de concurrencia
   distinguible y no pierde silenciosamente su edicion.

---

### User Story 3 - Ver matches deterministas con contribuciones (Priority: P1)

Como usuario, quiero que los resultados que veo cumplan siempre mis requisitos
duros y esten ordenados con criterios que puedo entender, para confiar en el
radar sin necesidad de revisar cada publicacion.

**Why this priority**: Hard filters puros, scoring determinista y runs
persistentes son el corazon del hito y el requisito previo de la explicabilidad
(H3) y las alertas (H5).

**Independent Test**: El conjunto de prueba verifica casos golden de hard
filters (incluidos desconocidos), determinismo del scoring, persistencia de
runs con congelamiento de inputs y listado de matches paginado sin repeticiones.

**Acceptance Scenarios**:

1. **Given** un radar activo con hard filters, **When** se ejecuta el run,
   **Then** solo pasan listings que cumplen todos los filtros y cada caso de
   valor desconocido respeta la politica versionada del perfil.
2. **Given** un listing sin precio y el filtro de presupuesto, **When** se
   aplica el filtro, **Then** el resultado es el que declara la politica del
   perfil y queda registrado, nunca un default silencioso.
3. **Given** el mismo perfil y el mismo conjunto de listings, **When** se
   ejecuta el run dos veces, **Then** el orden, los scores y el desglose de
   contribuciones son identicos.
4. **Given** el scoring baseline, **When** el usuario revisa un match, **Then**
   ve el score total en el radar y el desglose de contribuciones por dimension
   en el detalle del match, sin presentarlas como certeza.
5. **Given** un run falla despues de haber publicado el run previo, **When**
   termina, **Then** el ultimo run valido sigue siendo lo que se muestra, sin
   resultados parciales.
6. **Given** el usuario recorre las paginas del radar, **When** navega, **Then**
   no se repiten ni omiten matches y la posicion relativa es estable.
7. **Given** el usuario edita un radar activo, **When** se guarda, **Then** los
   resultados vigentes se marcan como obsoletos, se conservan para auditoria y
   un nuevo run los reemplaza.
8. **Given** un radar recien creado o editado, **When** el run se esta
   ejecutando, **Then** el radar muestra un estado de generacion de resultados
   distinguible de vacio y error, y publica los matches al completarse.

---

### User Story 4 - Explorar resultados en lista y mapa sincronizados (Priority: P2)

Como usuario, quiero revisar los matches en tarjetas, lista y mapa que se
sincronizan entre si, para comparar opciones por ubicacion sin perder contexto.

**Why this priority**: El mapa es una superficie de exploracion clave en CABA,
pero la lista/cards es el camino critico; el mapa debe respetar la precision
geografica autorizada para no prometer mas de lo que los datos soportan.

**Independent Test**: El recorrido de interfaz verifica cards/lista con datos
esenciales, sincronizacion lista-mapa, precision geografica de los puntos y
paginacion.

**Acceptance Scenarios**:

1. **Given** un radar con resultados, **When** el usuario explora en cards y
   lista, **Then** ve precio total, barrio, superficie, ambientes, score, fuente
   y estados, con paginacion.
2. **Given** la lista y el mapa sincronizados, **When** el usuario selecciona un
   match en uno, **Then** la seleccion se refleja en el otro.
3. **Given** un listing con precision de barrio o desconocida, **When** se
   renderiza en el mapa, **Then** el punto no revela coordenadas mas precisas
   que las autorizadas y la precision se indica.
4. **Given** un radar sin resultados, **When** se abre, **Then** se muestra un
   estado vacio claro con el siguiente paso sugerido.

---

### User Story 5 - Entender el detalle sin afirmaciones no soportadas (Priority: P2)

Como usuario, quiero ver el detalle completo de un listing (media, atributos,
fuente, ubicacion, datos faltantes y cambios conocidos) tal como los datos lo
soportan, para decidir sin que el sistema afirme cosas que no puede sostener.

**Why this priority**: El detalle es la superficie donde el usuario decide
contactar o no; afirmaciones cualitativas no soportadas son un riesgo de
confianza (politica de evidencia, UM-H0-007).

**Independent Test**: El recorrido de interfaz verifica el detalle sobre
listings completos, con datos faltantes y con cambios conocidos, y cubre todos
los estados de pantalla en desktop y mobile.

**Acceptance Scenarios**:

1. **Given** un match, **When** el usuario abre el detalle, **Then** ve media,
   atributos, fuente original, ubicacion, datos faltantes y cambios conocidos,
   sin afirmaciones no soportadas por los datos.
2. **Given** un listing con campos faltantes, **When** se muestra el detalle,
   **Then** los faltantes se indican explicitamente y no se completan con
   suposiciones.
3. **Given** una superficie en loading, empty, parcial, error recuperable, no
   autorizado o no encontrado, **When** ocurre ese estado, **Then** se distingue
   del resto y ofrece recuperacion o mensaje claro, en desktop y mobile.

---

### User Story 6 - Medir la activacion y verificar el recorrido E2E (Priority: P1)

Como persona responsable de producto y operaciones, quiero que cada accion del
radar emita su evento versionado y que el recorrido completo de un lote hasta el
detalle funcione sin duplicados, para medir la beta y confiar en el dato.

**Why this priority**: Los eventos alimentan la metrica de activacion y la
precision percibida (UM-H0-013, UM-H0-014); el E2E es la puerta de salida del
hito y cubre el guardrail de lineage completo (100%).

**Independent Test**: El conjunto de prueba verifica que cada accion declarada
emite su evento versionado sin PII, y que el recorrido lote a detalle es
correcto e idempotente al reimportar.

**Acceptance Scenarios**:

1. **Given** las acciones de activacion y exploracion (crear radar, run
   publicado, impresion, vista de detalle, apertura de fuente), **When** se
   ejecutan, **Then** cada una emite su evento versionado sin PII innecesaria.
2. **Given** un lote con registros validos e invalidos, **When** se recorre el
   E2E completo con el actor de prueba del harness, **Then** el reporte, las
   entidades Silver, el radar y los detalles son correctos, y reimportar el
   mismo lote produce 0 duplicados de listings ni matches.

### Edge Cases

- Un radar sin presupuesto, sin zonas o sin requisitos minimos debe rechazarse
  con errores accionables, no persistirse a medias.
- Una edicion concurrente del mismo radar debe comunicarse como error de
  concurrencia, no perderse en silencio.
- Un listing sin precio, sin zona o sin superficie debe tratarse segun la
  politica de desconocido del filtro correspondiente, nunca con un default
  silencioso.
- Un run fallido no debe dejar resultados parciales visibles ni reemplazar el
  ultimo run valido.
- Mientras un run se genera, el radar no debe mostrar "sin resultados" ni
  error; el estado de generacion es distinguible del vacio y del fallo.
- Un match con precision geografica desconocida no debe renderizarse en el mapa
  con coordenadas mas precisas que las autorizadas; puede mostrarse a nivel
  barrio o sin punto.
- Un radar sin resultados debe mostrar estado vacio, no confundirse con error o
  no autorizado.
- Al recorrer paginas con resultados que cambian entre runs, la paginacion debe
  ser estable: 0 matches repetidos u omitidos.
- Pausar y archivar no debe perder historial ni versiones previas del perfil.
- Editar un radar debe invalidar solo los resultados de ese radar, nunca los de
  otros radares del mismo usuario.
- El detalle de un listing sin media o con datos faltantes debe mostrarlo
  explicitamente, sin afirmaciones cualitativas.
- Reimportar el mismo lote (H2.1) no debe duplicar listings Silver ni generar
  matches nuevos.
- Un usuario sin permiso debe recibir "no autorizado" sin revelar datos ajenos.
- El rol operador no tiene acceso a radares de usuarios en este incremento; la
  verificacion E2E usa el actor de prueba del harness.
- El desglose de contribuciones solo aparece en el detalle del match, presentado
  como aproximacion sin certeza; las cards muestran solo el score total y el
  desglose nunca se presenta como explicacion con evidencia (eso es H3).
- Los eventos no deben contener PII innecesaria y deben emitirse con su version.

## Requirements *(mandatory)*

### Functional Requirements

#### Perfil y versiones

- **FR-001**: El sistema MUST permitir crear un radar (search profile) con
  nombre, operacion (alquiler), zonas de CABA, presupuesto, ambientes,
  superficie, estado y politica inicial.
- **FR-002**: Cada cambio del radar MUST producir una nueva version inmutable y
  MUST NO modificar versiones previas; cada run MUST referenciar la version del
  perfil que uso como input.
- **FR-003**: El estado de un radar MUST ser activo, pausado o archivado;
  pausar MUST detener la generacion de nuevos runs y archivar MUST ocultar la
  busqueda conservando todos sus datos e historial.

#### Casos de uso, ownership y contratos

- **FR-004**: Crear, listar, obtener, editar, pausar y archivar radares MUST
  respetar ownership con deny-by-default: solo el propietario puede operarlos;
  el rol operador MUST NO acceder a radares de usuarios en este incremento.
- **FR-005**: El sistema MUST validar el perfil antes de persistir (zonas CABA
  validas, presupuesto coherente, requisitos minimos) y MUST comunicar errores
  de validacion accionables, distinguibles de errores de concurrencia.
- **FR-006**: Una edicion concurrente del mismo radar MUST detectarse y
  comunicarse al usuario sin perdida silenciosa de cambios.

#### Onboarding y administracion

- **FR-007**: El onboarding MUST guiar al usuario por presupuesto, zonas y
  requisitos P0 con validacion accesible, y MUST exigir un resumen y
  confirmacion explicita antes de persistir.
- **FR-008**: El selector de radares MUST distinguir activos, pausados y
  archivados, MUST mantener el contexto del radar seleccionado en desktop y
  mobile, y MUST NO mezclar datos entre radares.

#### Hard filters y candidatos

- **FR-009**: Los hard filters (presupuesto, operacion, ubicacion, ambientes y
  requisitos obligatorios) MUST ser deterministas, sin embeddings ni modelos, y
  MUST pasar casos golden que declaren entrada, politica y resultado esperado.
- **FR-010**: Cada hard filter MUST declarar explicitamente como tratar valores
  desconocidos del listing y esa politica MUST quedar versionada con el radar.
- **FR-011**: La recuperacion de candidatos MUST aplicar los hard filters con
  paginacion estable: al recorrer paginas, 0 matches repetidos u omitidos.

#### Scoring y runs

- **FR-012**: El scoring baseline MUST ser deterministico y versionado, MUST
  ordenar los candidatos por fit objetivo con tie-break estable y MUST retornar
  contribuciones por dimension; el detalle del match MUST mostrar esas
  contribuciones sin presentarlas como certeza, y las cards y la lista MUST
  mostrar solo el score total.
- **FR-013**: Un run publicado MUST congelar el profile snapshot, el candidate
  set, la version de scoring y los tiempos; un run fallido MUST NO reemplazar el
  ultimo run valido ni dejar resultados parciales visibles.
- **FR-014**: Todo match expuesto MUST provenir de un run persistido y MUST
  incluir score, datos esenciales, fuente, precision geografica y lineage
  permitido.
- **FR-015**: Editar un radar activo MUST marcar los resultados vigentes como
  obsoletos y disparar un nuevo run, conservando los anteriores para auditoria.
- **FR-023**: La generacion de matches MUST ejecutarse de forma asincronica
  (job persistido): tras crear o editar el radar, el radar MUST mostrar un
  estado de generacion de resultados distinguible de vacio y error, y MUST
  publicar los matches al completarse el run.

#### Exploracion

- **FR-016**: El radar en lista y cards MUST mostrar precio total, barrio,
  superficie, ambientes, score, fuente y estados, con paginacion.
- **FR-017**: El mapa MUST sincronizar la seleccion con la lista, MUST
  representar cada match con una precision no mayor a la autorizada y MUST NO
  revelar coordenadas mas precisas que las del listing.
- **FR-018**: El detalle MUST mostrar media, atributos, fuente original,
  ubicacion, datos faltantes y cambios conocidos, sin afirmaciones
  cualitativas no soportadas por los datos.
- **FR-019**: Todas las superficies (onboarding, selector, radar, mapa y
  detalle) MUST distinguir loading, empty, parcial, error recuperable, no
  autorizado y no encontrado, en desktop y mobile, con acciones de
  recuperacion.

#### Instrumentacion y verificacion

- **FR-020**: Crear radar, run publicado, impresion, vista de detalle y apertura
  de fuente MUST emitir eventos versionados sin PII innecesaria, de acuerdo con
  el diccionario de eventos.
- **FR-021**: El recorrido E2E con un lote de validos e invalidos MUST producir
  reporte, entidades Silver, radar y detalles correctos; reimportar el mismo
  lote MUST producir 0 duplicados de listings ni matches.
- **FR-022**: Las superficies nuevas MUST ser operables por teclado y accesibles
  (nombres y contraste acordados), de acuerdo con el DoD del proyecto.

### Key Entities

- **Search Profile (Radar)**: busqueda persistente con nombre, operacion,
  zonas, presupuesto, ambientes, superficie, estado y politica inicial.
- **Search Profile Version**: snapshot inmutable del perfil usado como input de
  un run.
- **Hard Filter Policy**: regla determinista por filtro, incluida su politica de
  valores desconocidos, versionada con el radar.
- **Candidate Set**: conjunto de listings Silver que superan los hard filters de
  un run.
- **Scoring Baseline Policy**: version inmutable del ordenamiento por fit
  objetivo con tie-break y contribuciones.
- **Recommendation Run**: ejecucion persistida con profile snapshot, candidate
  set, version de scoring, tiempos y estado.
- **Recommendation Item (Match)**: par listing-run con score, posicion y
  contribuciones, persistido y consultable.
- **Match Views**: lista/cards y mapa del radar, sincronizados y paginados.
- **Listing Detail View**: detalle con media, atributos, fuente, ubicacion,
  faltantes y cambios conocidos.
- **Product Event**: registro versionado de activacion o exploracion sin PII
  innecesaria.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Crear un radar estructurado | UM-H2-019, UM-H2-020 (crear), UM-H2-021, UM-H2-022 |
| User Story 2 - Administrar las busquedas | UM-H2-020, UM-H2-021, UM-H2-023 |
| User Story 3 - Matches deterministas | UM-H2-024, UM-H2-025, UM-H2-026, UM-H2-027, UM-H2-028 |
| User Story 4 - Explorar lista y mapa | UM-H2-029, UM-H2-030 |
| User Story 5 - Detalle y estados | UM-H2-031, UM-H2-032 |
| User Story 6 - Medicion y E2E | UM-H2-033, UM-H2-034 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H2-019 | FR-001, FR-002, FR-003 | US1.1, US1.3, SC-001 |
| UM-H2-020 | FR-003, FR-004, FR-015 | US2.1-US2.5, US3.7, SC-001, SC-010 |
| UM-H2-021 | FR-005, FR-006 | US1.2, US2.5, SC-001 |
| UM-H2-022 | FR-007 | US1.1-US1.5, SC-010 |
| UM-H2-023 | FR-008 | US2.1-US2.4, SC-006 |
| UM-H2-024 | FR-009, FR-010 | US3.1-US3.2, SC-002 |
| UM-H2-025 | FR-011 | US3.6, SC-003 |
| UM-H2-026 | FR-012 | US3.3-US3.4, SC-003, SC-012 |
| UM-H2-027 | FR-013, FR-014, FR-015, FR-023 | US3.5, US3.7-US3.8, SC-004, SC-011, SC-013 |
| UM-H2-028 | FR-014 | US3.4-US3.6, SC-004 |
| UM-H2-029 | FR-016 | US4.1, SC-006 |
| UM-H2-030 | FR-017 | US4.2-US4.3, SC-005 |
| UM-H2-031 | FR-018 | US5.1-US5.2, SC-006 |
| UM-H2-032 | FR-019 | US5.3, SC-006 |
| UM-H2-033 | FR-020 | US6.1, SC-007 |
| UM-H2-034 | FR-021 | US6.2, SC-008 |

## Constitution Alignment *(mandatory)*

- **Persistent product objects**: radares, versiones de perfil, runs y matches
  son objetos persistentes; los resultados no viven solo en el chat ni en
  memoria. Esto sostiene matches persistentes y recomendaciones auditables.
- **Evidence and audit needs**: cada run congela inputs (profile snapshot,
  candidate set, version de scoring) y tiempos; cada match permite volver a su
  listing Silver, snapshot Bronze y parser; editar conserva versiones previas
  para auditoria. Sustenta el guardrail de lineage completo (100%).
- **Deterministic ranking**: el scoring baseline es puro, deterministico y
  versionado con tie-break estable; el ranking final nunca lo decide un LLM. La
  recuperacion de candidatos es filtrado duro sin embeddings.
- **Hard filters before any model**: los candidatos pasan primero por hard
  filters; nada generativo decide inclusion o exclusion.
- **Verification approach**: casos golden de hard filters, doble ejecucion para
  determinismo, fallo inducido de run, comparacion de precision geografica,
  recorrido de estados y accesibilidad en desktop/mobile, verificacion de
  eventos e idempotencia del E2E.
- **Dependency direction**: la UI consume contratos del Product API; la
  aplicacion usa dominio y puertos; el dominio no depende de FastAPI, DB, LLM
  ni UI. El scoring y los filtros son codigo determinista en la capa de
  aplicacion/dominio.
- **Minimal change**: el incremento se limita a UM-H2-019 a UM-H2-034 y excluye
  explicaciones con evidencia y feedback (H3), chat (H4), notificaciones (H5) y
  features Gold.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los radares creados en el conjunto de prueba queda
  persistido con estado y politica inicial; el 100% de las ediciones produce una
  version nueva sin modificar la anterior.
- **SC-002**: El 100% de los casos golden de hard filters (incluidos los de
  valores desconocidos) produce el resultado esperado; 0 resultados dependen del
  orden de ejecucion o de datos de otro usuario.
- **SC-003**: Ejecutar dos veces el mismo perfil sobre el mismo conjunto de
  listings produce exactamente el mismo orden, scores y desglose; 0 matches
  repetidos u omitidos al recorrer las paginas.
- **SC-004**: El 100% de los matches expuestos proviene de un run persistido con
  profile snapshot, candidate set, version de scoring y tiempos; 0 fallos de
  publicacion dejan resultados parciales visibles.
- **SC-005**: El 0% de los puntos del mapa supera la precision geografica
  autorizada del listing; el 100% de los matches indica su precision declarada.
- **SC-006**: El 100% de las superficies (onboarding, selector, radar, mapa y
  detalle) distingue loading, empty, parcial, error recuperable, no autorizado
  y no encontrado en desktop y mobile.
- **SC-007**: El 100% de las acciones de activacion y exploracion emite su
  evento versionado; 0 eventos contienen PII innecesaria.
- **SC-008**: El recorrido E2E del conjunto de prueba produce reporte, entidades
  Silver, radar y detalles correctos; reimportar el mismo lote produce 0
  duplicados de listings ni matches.
- **SC-009**: El 100% de las superficies nuevas es operable por teclado y pasa
  la revision de nombres y contraste acordada.
- **SC-010**: El 100% de los participantes del recorrido guiado completa crear
  radar, revisar matches y abrir un detalle sin asistencia en una sesion.
- **SC-011**: El 100% de los radares creados o editados muestra el estado de
  generacion de resultados mientras el run corre, distinguible de vacio y
  error, y publica los matches al completarse.
- **SC-012**: El 100% de los matches muestra en el detalle el desglose de
  contribuciones por dimension sin presentarlas como certeza, y las cards y la
  lista muestran solo el score total.
- **SC-013**: El 100% de los runs del conjunto de prueba publica sus matches en
  menos de 30 segundos desde que se dispara el run.

## Assumptions

- El alcance incluye exactamente UM-H2-019 a UM-H2-034 (Epica H2.3 - Busqueda,
  matching baseline y radar). La explicacion con evidencia, el feedback, la
  comparacion estructurada y el historial visible son H3; el chat es H4; las
  alertas son H5.
- Los listings Silver de H2.2 (incluida la precision geografica
  exact/block/barrio/aproximada/desconocida) y el reporte de calidad de H2.1 ya
  estan disponibles como entrada.
- El incremento asume disponibilidad de identidad y roles (H1.3) para el
  ownership; si ese incremento no esta cerrado al verificar, el recorrido E2E
  usa el actor de prueba del harness.
- El rol operador no tiene superficie sobre radares de usuarios en este
  incremento: la verificacion E2E usa el actor de prueba del harness y la
  consola operativa pertenece a H6.
- El diccionario de eventos (UM-H0-013) no existe aun como contrato publicado;
  este incremento define un contrato minimo versionado (crear radar, run
  publicado, impresion, vista, fuente abierta) alineado al diccionario del
  backlog, sin PII innecesaria.
- El scoring baseline es intencionalmente simple (fit objetivo por presupuesto,
  zonas, ambientes y superficie con contribuciones visibles y tie-break
  estable); el scoring completo con criterios, pesos, confianza y evidencia es
  H3 (UM-H3-012 a UM-H3-016). Las contribuciones se muestran como desglose
  simple en el detalle del match, sin evidencia; las cards muestran solo el
  score total.
- "Pausar" detiene la generacion de nuevos runs; "archivar" oculta la busqueda
  conservando datos e historial. La reanudacion conserva las versiones previas.
- Editar un radar activo invalida sus resultados vigentes y dispara un nuevo
  run; los runs anteriores se conservan para auditoria.
- Los runs se ejecutan de forma asincronica (job persistido): el radar muestra
  "generando resultados" mientras corre y publica los matches al completarse;
  esto no altera el determinismo del scoring ni la congelacion de inputs.
- Los runs sobre el conjunto de prueba del harness publican sus matches en
  menos de 30 segundos desde que se disparan; el umbral se mide hasta que los
  matches quedan visibles en el radar.
- El mapa se alimenta de la precision declarada por Silver: no se geocodifican
  en este incremento coordenadas mas precisas (la geocodificacion de H2.2 es P1
  y respeta la precision).
- El tamano de pagina y los detalles de paginacion estable se deciden en el
  plan; esta spec exige 0 repetidos/omitidos y orden estable.
- El feedback (like/dislike/save), la comparacion de listings, las
  notificaciones y la superficie de consola operativa quedan fuera de alcance.
- La verificacion E2E y de estados se ejecuta sobre el conjunto de prueba del
  harness y un recorrido de interfaz automatizado en desktop y mobile, de
  acuerdo con el DoD del proyecto (accesibilidad incluida).
