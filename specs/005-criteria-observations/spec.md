# Feature Specification: Criteria and Observations

**Feature Branch**: `005-criteria-observations`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "Arranquemos con la especificacion de la epica H3.1 - Criterios y observaciones del backlog, con alcance exacto UM-H3-001 a UM-H3-011."

## Clarifications

### Session 2026-08-06

- Q: ¿Cuantas observaciones vigentes puede tener un mismo listing para un mismo
  concepto y fuente? → A: Una sola observacion vigente por (listing, concepto,
  fuente); las versiones previas quedan como historial para auditoria y la
  recomputacion reemplaza la vigente.
- Q: ¿Quien o que dispara una recomputacion selectiva cuando cambia la version
  de un parser, prompt, modelo o concepto? → A: La invalidacion de las
  observaciones afectadas es automatica al registrarse el cambio de version; el
  recomputo lo dispara el operador manualmente como job con causa registrada.
- Q: ¿Donde se ejecuta la extraccion cualitativa que usa el modelo con salida
  estructurada? → A: Proveedor externo gestionado (API del proveedor) con el
  input limitado a los campos permitidos del listing normalizado; nunca PII de
  usuarios ni raw HTML.
- Q: ¿Este incremento expone contratos HTTP de Product API, o los conceptos,
  criterios y observaciones se gestionan por dominio y jobs y se verifican solo
  con el harness? → A: Sin contratos HTTP nuevos: dominio + jobs + harness; la
  curaduria inicial entra como seed versionado y el recompute se dispara por el
  mecanismo de jobs existente.

Las decisiones por default (sin superficie de UI/consola, proveedor de
extraccion cualitativa diferido al plan/ADR, embeddings y contexto urbano como
P1 dentro del alcance de la epica) estan documentadas en
[Assumptions](#assumptions).

## Operational Definitions

- **Concepto curado**: entidad canonica de la taxonomia de criterios (por
  ejemplo, balcon, ambientes, piso, tipo de cocina, zonas) con nombre canonico,
  aliases, matcher type, fuente, defaults y politica de computo. Es la base
  versionada sobre la que se declaran preferencias y se extraen observaciones.
- **Matcher type**: tipo de evaluador que un criterio o una observacion puede
  usar (por ejemplo, rango numerico, categorico, proximidad geografica, feature
  semantica). En este incremento se registran y validan los tipos y sus
  parametros permitidos; los evaluadores en si son H3.2.
- **Preference fact**: hecho declarado sobre las preferencias de un usuario con
  valor, peso, polaridad, confianza, fuente, estado de validez y alcance por
  busqueda. Es inmutable: un cambio genera un fact nuevo o una compensacion
  trazable.
- **Memoria semantica**: contenido del perfil que no es evaluable directamente
  (contexto conversacional, matices); no se convierte en instrucciones sin
  pasar por una compilacion validada.
- **Criterio ejecutable**: instruccion evaluable derivada de preference facts y
  conceptos curados, con matcher type y parametros validados contra el
  registry. Es lo unico que el motor de scoring (H3.2) puede evaluar.
- **Compilacion de criterios**: conjunto ordenado y versionado de criterios
  ejecutables producido a partir de ediciones, con advertencias explicitas;
  convertir preferencias blandas en hard filters requiere confirmacion.
- **Observacion de listing**: hecho extraido de un listing normalizado que
  conserva concepto, valor, score, confianza, evidencia, fuente (regla o
  modelo), version de extraccion y timestamp. A lo sumo una observacion esta
  vigente por (listing, concepto, fuente); las versiones previas quedan como
  historial para auditoria.
- **Evidencia de fragmento**: cita del texto normalizado del listing que
  soporta una observacion objetiva.
- **Extraccion objetiva**: extraccion por reglas deterministicas (balcon,
  ambientes, piso, tipo de cocina y otras senales textuales verificables) con
  casos golden y evidencia de fragmento.
- **Extraccion cualitativa**: extraccion por modelo con salida estructurada
  limitada a los esquemas permitidos por concepto; el modelo produce valor,
  evidencia y confianza, y nunca decide inclusion, ranking ni notificaciones.
- **Input permitido**: subconjunto de campos del listing normalizado autorizado
  para enviar al servicio de extraccion; nunca incluye PII de usuarios ni raw
  HTML.
- **Recomputacion selectiva**: invalidacion y recomputo solo de las
  observaciones afectadas por un cambio de version de parser, prompt, modelo o
  concepto; las observaciones no afectadas no cambian y las versiones previas
  usadas se conservan.
- **Señal urbana**: dato de contexto (cafes, transporte, espacios verdes) con
  fuente, fecha, geometria y algoritmo registrados, vinculado a un listing y
  respetando la precision geografica autorizada.
- **Lineage de observacion**: para cada observacion se puede volver al listing
  Silver, al snapshot Bronze y a la version de extraccion (regla, modelo,
  prompt y schema) que la produjo.

## Review and Measurement Protocol

- La puerta de salida del hito: cada recomendacion se reconstruye desde perfil,
  listing, features, scoring y evidencia. Este incremento entrega la capa Gold
  de criterios y observaciones; el scoring (H3.2), las explicaciones (H3.2), el
  feedback (H3.3) y la revision de fairness (H3.4) NO se evaluan aqui.
- La curaduria de conceptos se verifica con casos golden de registro y edicion:
  cada cambio produce una version nueva, los alias resuelven a un unico
  concepto canonico y los matcher types o parametros no soportados se rechazan.
- La compilacion de criterios se verifica comparando ediciones contra el
  resultado esperado: orden, version, advertencias y rechazo de criterios
  invalidos; la conversion de preferencias blandas en hard filters sin
  confirmacion debe fallar.
- La extraccion objetiva se verifica con casos golden por regla (balcon,
  ambientes, piso, tipo de cocina): entrada, fragmento esperado y valor
  esperado; ejecutar dos veces la misma regla sobre el mismo listing produce
  resultados identicos.
- La extraccion cualitativa se verifica con outputs validos e invalidos: los
  invalidos se rechazan o reintentan con un maximo acotado y quedan
  consultables con causa; el 100% de las observaciones generativas referencia
  versiones inmutables de modelo, prompt y schema y permite reproducir su input
  permitido. La postura de proveedor externo gestionado se verifica confirmando
  que el input enviado se limita a los campos permitidos y que 0 llamadas
  contienen PII de usuarios o raw HTML.
- La recomputacion selectiva se verifica induciendo un cambio de version de
  parser, prompt, modelo o concepto: las observaciones afectadas se invalidan
  automaticamente, solo ellas se recomputan cuando el operador dispara el job,
  las no afectadas quedan intactas y las versiones previas usadas siguen
  consultables.
- El lineage se verifica recorriendo observacion -> listing Silver -> snapshot
  Bronze -> version de extraccion para el 100% de las observaciones del
  conjunto de prueba (guardrail de lineage completo).
- Los embeddings (P1) se verifican confirmando que se indexa solo texto y
  features permitidos del listing normalizado con modelo y version registrados,
  y 0 casos desde raw HTML o PII.
- El contexto urbano (P1) se verifica confirmando fuente, fecha, geometria y
  algoritmo en el 100% de las señales, y el respeto de la precision geografica
  autorizada.
- La instrumentacion se verifica confirmando que observaciones y recomputes
  emiten sus eventos versionados sin PII innecesaria.
- Este incremento no expone superficies de UI, consola operativa ni contratos
  HTTP nuevos: la verificacion se ejecuta sobre el conjunto de prueba del
  harness con casos golden, jobs de extraccion y tests de dominio; la consola
  operativa es H6.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Curar la taxonomia de conceptos (Priority: P1)

Como equipo de producto y datos, quiero registrar y versionar conceptos curados
con aliases, matcher type, defaults y politica de computo, para que
preferencias, observaciones y scoring futuro hablen el mismo idioma.

**Why this priority**: Sin un registro canonico versionado no hay forma
confiable de comparar lo que el usuario pide con lo que se observa en los
listings; es la base de la explicabilidad de H3.

**Independent Test**: El conjunto de prueba registra y edita conceptos y
verifica que cada cambio produce una version nueva, que los alias resuelven a
un unico concepto canonico y que los matcher types o parametros no soportados
se rechazan.

**Acceptance Scenarios**:

1. **Given** un concepto curado con nombre canonico, aliases, matcher type,
   fuente, defaults y politica de computo, **When** se registra, **Then**
   queda persistido con su version y es consultable por nombre o alias.
2. **Given** un concepto existente, **When** se edita, **Then** se crea una
   version nueva inmutable y la anterior queda intacta y consultable.
3. **Given** un alias que colisiona con otro concepto, **When** se registra o
   edita, **Then** se emite una advertencia explicita y el alias no queda
   ambiguo.
4. **Given** un concepto con matcher type o parametros no soportados, **When**
   se registra o edita, **Then** se rechaza con un error accionable sin
   persistir datos parciales.

---

### User Story 2 - Declarar preferencias y compilar criterios ejecutables (Priority: P1)

Como usuario representado por su radar, quiero que mis preferencias queden como
hechos con valor, peso, polaridad, confianza y alcance, y que solo se vuelvan
instrucciones evaluables despues de una compilacion validada, para que el
sistema nunca confunda memoria conversacional con criterios que debe aplicar.

**Why this priority**: Es la separacion entre memoria semantica e instrucciones
evaluables que evita que el chat mute silenciosamente el radar y que
preferencias blandas se vuelvan filtros duros sin confirmacion.

**Independent Test**: El conjunto de prueba crea y versiona preference facts,
compila ediciones a criterios ejecutables con advertencias y verifica el
rechazo de criterios invalidos y de conversiones blandas a duras sin
confirmacion.

**Acceptance Scenarios**:

1. **Given** una preferencia declarada para una busqueda, **When** se persiste,
   **Then** queda como preference fact con valor, peso, polaridad, confianza,
   fuente, estado de validez y alcance, vinculado a su busqueda.
2. **Given** un cambio de decision del usuario, **When** se registra, **Then**
   se crea un fact nuevo (o compensacion trazable) sin mutar el anterior.
3. **Given** ediciones de criterios, **When** se compilan, **Then** se produce
   un conjunto ordenado y versionado de criterios ejecutables con advertencias
   explicitas y referencia al concepto y matcher type validados.
4. **Given** contenido de memoria semantica no evaluable, **When** se compila,
   **Then** no se convierte en criterio ejecutable sin una edicion explicita
   validada.
5. **Given** una preferencia blanda que implicaria un hard filter, **When** se
   compila sin confirmacion, **Then** la conversion se rechaza y se pide
   confirmacion explicita.

---

### User Story 3 - Observar listings con reglas objetivas (Priority: P1)

Como consumidor de datos del radar, quiero observaciones objetivas (balcon,
ambientes, piso, tipo de cocina y otras senales textuales verificables)
extraidas por reglas deterministicas con evidencia de fragmento, para que
ninguna afirmacion sobre un listing dependa de la interpretacion de un modelo.

**Why this priority**: Las observaciones objetivas son el piso de confianza del
matching: sin reglas verificables, cualquier afirmacion posterior (incluida la
cualitativa) queda sin ancla.

**Independent Test**: El conjunto de prueba ejecuta las reglas sobre casos
golden y verifica valor esperado, fragmento de evidencia y determinismo (doble
ejecucion identica).

**Acceptance Scenarios**:

1. **Given** un listing con texto normalizado, **When** se ejecuta una regla
   objetiva, **Then** se produce una observacion con concepto, valor, score,
   confianza, evidencia de fragmento, fuente regla, version y timestamp.
2. **Given** los casos golden de balcon, ambientes, piso y tipo de cocina,
   **When** se ejecutan las reglas, **Then** cada caso produce el valor esperado
   con el fragmento de evidencia esperado.
3. **Given** el mismo listing y la misma version de reglas, **When** se ejecuta
   dos veces, **Then** ambas ejecuciones producen observaciones identicas.

---

### User Story 4 - Extraer features cualitativas con salida estructurada versionada (Priority: P1)

Como equipo de producto, quiero que el modelo extraiga features cualitativas
solo dentro de esquemas permitidos, con evidencia, confianza y versiones
inmutables de modelo, prompt y schema, para que el resultado sea auditable,
reproducible y nunca invente campos.

**Why this priority**: La extraccion generativa es el punto donde el LLM toca
datos de producto; sin schema estricto, versionado y rechazo de outputs
invalidos no hay confianza en lo que despues alimentara el scoring.

**Independent Test**: El conjunto de prueba ejecuta extracciones validas e
invalidas y verifica rechazo/reintento acotado, referencias de version
inmutables y reproducibilidad del input permitido.

**Acceptance Scenarios**:

1. **Given** un listing y un concepto cualitativo, **When** se ejecuta la
   extraccion, **Then** el modelo produce solo el esquema permitido con valor,
   evidencia y confianza.
2. **Given** un output fuera del esquema permitido o sin evidencia, **When** se
   valida, **Then** se rechaza o reintenta con un maximo acotado y el fallo
   queda consultable con su causa.
3. **Given** una observacion generativa, **When** se audita, **Then** referencia
   versiones inmutables de modelo, prompt y schema y permite reproducir el
   input permitido que la produjo.
4. **Given** la extraccion cualitativa, **When** se ejecuta, **Then** el input
   enviado se limita a los campos permitidos del listing normalizado y nunca
   incluye PII de usuarios ni raw HTML.

---

### User Story 5 - Recomputar solo lo afectado por un cambio (Priority: P1)

Como equipo de datos y operaciones, quiero que un cambio de parser, prompt,
modelo o concepto invalide y recompute solo las observaciones afectadas
conservando las versiones previas, para que un upgrade no degrade ni borre
historia y el impacto sea proporcional al cambio.

**Why this priority**: La recomputacion selectiva es lo que hace viable
versionar y mejorar extracciones en beta sin re-procesar todo ni perder
auditoria.

**Independent Test**: El conjunto de prueba induce cambios de version de
parser, prompt, modelo y concepto y verifica que solo se recomputan las
observaciones afectadas, que las no afectadas no cambian y que las versiones
previas usadas quedan consultables.

**Acceptance Scenarios**:

1. **Given** un cambio de version de parser, prompt, modelo o concepto, **When**
   se registra, **Then** las observaciones afectadas se invalidan
   automaticamente y las no afectadas quedan intactas.
2. **Given** observaciones invalidadas por el cambio, **When** el operador
   dispara el recomputo, **Then** solo las afectadas se recomputan con causa
   registrada y las versiones previas usadas quedan consultables.
3. **Given** la recomputacion, **When** termina, **Then** queda registrado el
   job con estado, conteos, causa y tiempos, y las versiones previas usadas
   siguen consultables para auditoria.
4. **Given** observaciones obsoletas por el cambio, **When** un consumidor pide
   observaciones vigentes, **Then** no se usan en resultados nuevos sin un
   recomputo valido.

---

### User Story 6 - Indexar embeddings de listings normalizados (Priority: P1)

Como equipo de datos, quiero embeddings generados solo desde texto y features
permitidos del listing normalizado, con modelo y version registrados, para que
la busqueda semantica futura nunca se apoye en raw HTML ni PII.

**Why this priority**: Es P1 del backlog: prepara la recuperacion semantica sin
ser camino critico; los hard filters y el ranking determinista no dependen de
esto.

**Independent Test**: El conjunto de prueba indexa listings permitidos y
verifica modelo y version registrados, y 0 embeddings desde raw HTML o PII.

**Acceptance Scenarios**:

1. **Given** un listing normalizado, **When** se genera su embedding, **Then**
   se indexa solo el texto y las features permitidos, con modelo y version
   registrados.
2. **Given** raw HTML o PII en un origen, **When** se indexa, **Then** 0
   embeddings se generan desde esos contenidos.
3. **Given** una recomputacion selectiva, **When** cambia el modelo o el texto
   permitido, **Then** solo los embeddings afectados se regeneran y las
   versiones previas usadas quedan registradas.

---

### User Story 7 - Incorporar contexto urbano con trazabilidad (Priority: P1)

Como usuario del radar, quiero que el contexto del barrio (cafes, transporte,
espacios verdes) llegue con fuente, fecha, geometria y algoritmo, para poder
confiar en senales que no provienen del propio listing.

**Why this priority**: Es P1 del backlog: enriquece el matching sin bloquear el
camino critico; cada senal debe ser auditable y respetar la precision
geografica.

**Independent Test**: El conjunto de prueba verifica que el 100% de las senales
urbanas tiene fuente, fecha, geometria y algoritmo, y que la consulta externa
es cacheada con limites.

**Acceptance Scenarios**:

1. **Given** un listing en un barrio cubierto, **When** se incorpora contexto,
   **Then** cada senal queda con fuente, fecha, geometria y algoritmo
   registrados y vinculada al listing.
2. **Given** consultas externas repetidas, **When** se ejecutan, **Then** se
   sirven desde cache y se respetan los limites de la fuente.
3. **Given** una senal con precision inferior a la autorizada del listing,
   **When** se usa, **Then** no se presenta mas precisa de lo que la fuente
   declara.

### Edge Cases

- Un concepto sin matcher type o con parametros no soportados debe rechazarse,
  no persistirse a medias.
- Alias colisionantes deben advertirse y no quedar ambiguos.
- Una preferencia sin confianza o fuente debe persistirse con esos campos
  explicitos, no con valores inventados.
- Memoria semantica nunca debe compilarse como criterio ejecutable sin una
  edicion explicita validada.
- Una preferencia blanda no debe convertirse en hard filter sin confirmacion.
- Un listing sin texto suficiente para una regla objetiva produce "sin
  evidencia" explicito, no una observacion inventada.
- Un output generativo invalido se rechaza o reintenta con maximo acotado y
  queda consultable; no se guarda silenciosamente.
- Una recomputacion no debe tocar observaciones de otro concepto, otra fuente o
  otra version no afectada.
- Un job de recomputacion fallido no debe dejar observaciones a medias ni
  borrar versiones previas.
- Las observaciones obsoletas no deben usarse en resultados nuevos sin
  recomputo valido.
- El texto enviado a extraccion y embeddings nunca incluye PII de usuarios ni
  raw HTML.
- Las señales urbanas sin fuente, fecha, geometria o algoritmo no deben usarse
  como si tuvieran trazabilidad.
- Este incremento no expone UI ni consola operativa: el operador no tiene
  superficie sobre conceptos ni observaciones de usuarios (H6); la verificacion
  usa el actor de prueba del harness.
- El registro de un concepto con mismo nombre que una version previa debe
  generar una version nueva, nunca una mutacion.
- Una nueva extraccion para el mismo (listing, concepto, fuente) debe reemplazar
  la observacion vigente y conservar la previa como historial, nunca dejar dos
  vigentes ambiguas.
- Un cambio de version debe invalidar automaticamente las observaciones
  afectadas aunque el operador no haya disparado aun el recomputo; hasta
  entonces no se usan en resultados nuevos.

## Requirements *(mandatory)*

### Functional Requirements

#### Concept registry

- **FR-001**: El sistema MUST permitir registrar conceptos curados con nombre
  canonico, aliases, matcher type, fuente, defaults y politica de computo; cada
  cambio MUST producir una version inmutable sin modificar versiones previas.
- **FR-002**: Los matcher types y sus parametros permitidos MUST validarse
  contra el conjunto soportado; registros o ediciones invalidas MUST
  rechazarse con error accionable sin persistir datos parciales.
- **FR-003**: Los aliases MUST resolverse a un unico concepto canonico; una
  colision de alias MUST emitir una advertencia explicita y no quedar ambigua.

#### Preference facts

- **FR-004**: Los preference facts MUST persistir valor, peso, polaridad,
  confianza, fuente, estado de validez y alcance por busqueda; un cambio de
  decision MUST generar un fact nuevo o una compensacion trazable sin mutar el
  anterior.
- **FR-005**: Los preference facts MUST estar vinculados a su busqueda y
  usuario, con acceso deny-by-default.

#### Criterios ejecutables y compilacion

- **FR-006**: Los criterios del perfil MUST separar memoria semantica (no
  evaluable) de instrucciones ejecutables; solo estas ultimas MUST ser
  evaluables por el motor de matching.
- **FR-007**: La compilacion de ediciones MUST producir un conjunto ordenado y
  versionado de criterios ejecutables con advertencias explicitas, y MUST NO
  convertir preferencias blandas en hard filters sin confirmacion explicita.
- **FR-008**: Cada criterio ejecutable MUST referenciar su concepto, matcher
  type y parametros validados, y la version de su edicion o fact de origen.

#### Observaciones y extraccion

- **FR-009**: Cada observacion de listing MUST persistir concepto, valor, score,
  confianza, evidencia, fuente (regla o modelo), version de extraccion y
  timestamp; a lo sumo una observacion MUST estar vigente por (listing,
  concepto, fuente) y las versiones previas MUST conservarse como historial.
- **FR-010**: La extraccion objetiva MUST ser determinista (reglas) con casos
  golden, y cada observacion objetiva MUST conservar evidencia de fragmento del
  texto normalizado; sin fragmento, la observacion MUST declarar "sin
  evidencia" en lugar de inventarse.
- **FR-011**: La extraccion cualitativa MUST limitarse a los esquemas permitidos
  por concepto y MUST NO decidir inclusion o exclusion de candidatos, ranking
  ni notificaciones.
- **FR-012**: Los outputs generativos invalidos (fuera de esquema o sin
  evidencia) MUST rechazarse o reintentarse con un maximo acotado de intentos,
  y los fallos MUST quedar consultables con su causa.
- **FR-013**: Cada observacion generativa MUST referenciar versiones inmutables
  de modelo, prompt y schema, y MUST permitir reproducir el input permitido que
  la produjo.
- **FR-014**: La extraccion cualitativa MUST ejecutarse en un proveedor externo
  gestionado, y el input enviado MUST limitarse a los campos permitidos del
  listing normalizado; MUST NO incluir PII de usuarios ni raw HTML.

#### Recomputacion selectiva

- **FR-015**: Un cambio de version de parser, prompt, modelo o concepto MUST
  invalidar automaticamente solo las observaciones afectadas; las no afectadas
  MUST NO modificarse y las versiones previas usadas MUST conservarse para
  auditoria. El recomputo MUST dispararse manualmente por el operador como job
  con causa registrada.
- **FR-016**: Las recomputaciones MUST ejecutarse como jobs versionados con
  estado, conteos, causa y tiempos registrados; un job fallido MUST NO dejar
  observaciones a medias ni borrar versiones previas.
- **FR-017**: Las observaciones obsoletas por un cambio de version MUST NO
  usarse en resultados nuevos sin un recomputo valido.

#### Embeddings (P1)

- **FR-018**: Los embeddings MUST generarse solo desde texto y features
  permitidos del listing normalizado, con modelo y version registrados, y MUST
  NO indexarse desde raw HTML ni PII.
- **FR-019**: Un cambio de modelo o de texto permitido MUST regenerar solo los
  embeddings afectados, registrando las versiones previas usadas.

#### Contexto urbano (P1)

- **FR-020**: Cada señal urbana MUST persistir fuente, fecha, geometria y
  algoritmo, y MUST vincularse al listing correspondiente sin superar la
  precision geografica autorizada.
- **FR-021**: Las consultas externas de contexto MUST servirse con cache y
  respetar los limites de la fuente.

#### Transversal

- **FR-022**: Las observaciones y las recomputaciones MUST emitir eventos
  versionados de auditoria/telemetria sin PII innecesaria.
- **FR-023**: El 100% de las observaciones MUST permitir recorrer lineage:
  observacion -> listing Silver -> snapshot Bronze -> version de extraccion.
- **FR-024**: Este incremento MUST NO exponer superficies de UI, consola
  operativa ni contratos HTTP nuevos sobre conceptos, criterios u observaciones:
  la curaduria inicial entra como seed versionado, el recompute se dispara por
  el mecanismo de jobs existente y la verificacion se ejecuta sobre el conjunto
  de prueba del harness (la consola operativa es H6).

### Key Entities

- **Concept**: concepto curado con nombre canonico, aliases, matcher type,
  fuente, defaults y politica de computo.
- **Concept Version**: version inmutable de un concepto; los cambios crean
  versiones nuevas.
- **Preference Fact**: hecho de preferencia con valor, peso, polaridad,
  confianza, fuente, validez y alcance por busqueda.
- **Profile Criterion (ejecutable)**: instruccion evaluable con matcher type y
  parametros validados, separada de la memoria semantica.
- **Criterion Compilation**: conjunto ordenado y versionado de criterios con
  advertencias y confirmaciones registradas.
- **Listing Observation**: hecho extraido con concepto, valor, score, confianza,
  evidencia, fuente, version y timestamp.
- **Extraction Rule**: regla determinista de extraccion objetiva con casos
  golden y evidencia de fragmento.
- **Extraction Version**: version inmutable de modelo, prompt o schema usada por
  la extraccion cualitativa.
- **Recomputation Run**: job versionado que invalida y recomputa observaciones
  afectadas con estado, conteos, causa y tiempos.
- **Embedding Index Entry**: vector de texto/features permitidos con modelo y
  version registrados.
- **Urban Signal**: contexto de barrio con fuente, fecha, geometria y algoritmo.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Curar la taxonomia | UM-H3-001 |
| User Story 2 - Preferencias y criterios | UM-H3-002, UM-H3-003, UM-H3-004 |
| User Story 3 - Observaciones objetivas | UM-H3-005, UM-H3-006 |
| User Story 4 - Extraccion cualitativa | UM-H3-007, UM-H3-008 |
| User Story 5 - Recomputacion selectiva | UM-H3-011 |
| User Story 6 - Embeddings indexados | UM-H3-009 |
| User Story 7 - Contexto urbano | UM-H3-010 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H3-001 | FR-001, FR-002, FR-003 | US1.1-US1.4, SC-001, SC-002 |
| UM-H3-002 | FR-004, FR-005 | US2.1-US2.2, SC-005 |
| UM-H3-003 | FR-006, FR-008 | US2.3-US2.4, SC-005 |
| UM-H3-004 | FR-007 | US2.5, SC-005 |
| UM-H3-005 | FR-009 | US3.1, US4.1, SC-003, SC-006, SC-012 |
| UM-H3-006 | FR-010 | US3.2-US3.3, SC-002, SC-004 |
| UM-H3-007 | FR-011, FR-012 | US4.1-US4.2, SC-003 |
| UM-H3-008 | FR-013, FR-014 | US4.3-US4.4, SC-003, SC-006 |
| UM-H3-009 | FR-018, FR-019 | US6.1-US6.3, SC-007 |
| UM-H3-010 | FR-020, FR-021 | US7.1-US7.3, SC-008 |
| UM-H3-011 | FR-015, FR-016, FR-017 | US5.1-US5.4, SC-004, SC-009 |
| Transversal (todos) | FR-022, FR-023, FR-024 | SC-006, SC-010, SC-011 |

## Constitution Alignment *(mandatory)*

- **Persistent product objects**: conceptos, preference facts, criterios
  ejecutables y observaciones son objetos persistentes y versionados; nada de
  lo que alimenta el matching vive solo en el chat. Sustenta la capa Gold de la
  arquitectura de datos.
- **Evidence and audit needs**: cada observacion conserva evidencia, fuente,
  version de extraccion y timestamp; cada observacion generativa referencia
  versiones inmutables de modelo, prompt y schema y permite reproducir su input
  permitido; la recomputacion preserva versiones previas usadas. Sustenta el
  guardrail de lineage completo (100%) y la politica de evidencia (UM-H0-007).
- **Deterministic matching**: las reglas objetivas son deterministicas con
  casos golden; el modelo de extraccion cualitativa solo produce esquemas
  permitidos con evidencia y confianza y nunca decide inclusion, ranking ni
  notificaciones; el ranking final sigue siendo codigo deterministico (H3.2).
- **Versioned prompts, models and schemas**: toda extraccion generativa
  referencia versiones inmutables y permite reproducir el input permitido; los
  cambios de version disparan recomputacion selectiva (UM-H3-011).
- **Verification approach**: casos golden de registry y reglas objetivas, doble
  ejecucion para determinismo, outputs generativos validos e invalidos con
  reintento acotado, recomputacion inducida por cambio de version, recorrido de
  lineage y verificacion de eventos sin PII.
- **Dependency direction**: el registry, los criterios y las observaciones son
  dominio/aplicacion; los adapters de extraccion (reglas y modelo) implementan
  puertos; el dominio no depende de FastAPI, DB, LLM ni UI.
- **Minimal change**: el incremento se limita a UM-H3-001 a UM-H3-011 y excluye
  scoring y explicaciones (H3.2), feedback (H3.3), calidad del matching (H3.4),
  chat (H4) y notificaciones (H5). Embeddings y contexto urbano son P1.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los cambios de conceptos del conjunto de prueba queda
  versionado; 0 mutaciones de versiones previas.
- **SC-002**: El 100% de los casos golden de extraccion objetiva (balcon,
  ambientes, piso, tipo de cocina) produce el valor esperado con su fragmento
  de evidencia; 0 observaciones objetivas sin evidencia o con evidencia
  incorrecta.
- **SC-003**: El 100% de las observaciones cualitativas cumple el esquema
  permitido, con evidencia, confianza y versiones de modelo/prompt/schema
  registradas; 0 observaciones con version desconocida; el 100% de los outputs
  invalidos se rechaza o reintenta con maximo acotado y queda consultable.
- **SC-004**: Ejecutar dos veces la misma regla sobre el mismo listing produce
  observaciones identicas; un cambio de version de parser, prompt, modelo o
  concepto invalida automaticamente solo las observaciones afectadas, el 0% de
  las no afectadas cambia y el 100% de las versiones previas usadas queda
  consultable; el recomputo de las afectadas se completa cuando el operador lo
  dispara.
- **SC-005**: El 100% de los criterios ejecutables de las compilaciones
  publicadas tiene matcher type y parametros validados; 0 criterios invalidos en
  compilaciones publicadas; el 100% de las conversiones blandas a duras requiere
  confirmacion explicita registrada.
- **SC-006**: El 100% de las observaciones del conjunto de prueba permite
  recorrer lineage observacion -> listing Silver -> snapshot Bronze -> version
  de extraccion.
- **SC-007**: El 100% de los embeddings se genera desde texto y features
  permitidos con modelo y version registrados; 0 embeddings desde raw HTML o
  PII.
- **SC-008**: El 100% de las señales urbanas tiene fuente, fecha, geometria y
  algoritmo registrados y respeta la precision geografica autorizada.
- **SC-009**: El 100% de los jobs de recomputacion registra estado, conteos,
  causa y tiempos; 0 jobs fallidos dejan observaciones a medias o borran
  versiones previas.
- **SC-010**: El 100% de las observaciones y recomputaciones emite su evento
  versionado; 0 eventos contienen PII innecesaria.
- **SC-011**: El 100% de las superficies del harness cubre los casos golden del
  incremento sin superficies de UI, consola operativa ni contratos HTTP nuevos;
  0 accesos de operador a conceptos u observaciones de usuarios.
- **SC-012**: El 100% de los pares (listing, concepto, fuente) del conjunto de
  prueba tiene a lo sumo una observacion vigente; 0 pares con observaciones
  vigentes ambiguas.
- **SC-013**: El 100% de las llamadas de extraccion cualitativa se ejecuta
  contra el proveedor externo gestionado con input limitado a los campos
  permitidos; 0 llamadas contienen PII de usuarios o raw HTML.

## Assumptions

- El alcance incluye exactamente UM-H3-001 a UM-H3-011 (Epica H3.1 - Criterios
  y observaciones). El scoring con evaluadores y policy (H3.2, UM-H3-012 a
  UM-H3-016), las explicaciones y el comparador (H3.2, UM-H3-018 a UM-H3-022),
  el feedback (H3.3), la calidad del matching (H3.4), el chat (H4) y las
  alertas (H5) quedan fuera y se especifican en sus propios incrementos.
- Los listings Silver de H2.2 (atributos normalizados, texto, precision
  geografica) y el dataset controlado de H0.2 ya estan disponibles como
  entrada; las observaciones son la primera capa Gold previa al scoring.
- Este incremento no incluye superficies de UI, consola operativa ni contratos
  HTTP nuevos (el backlog no asigna stories WEB/OPS ni de contratos a H3.1):
  la curaduria inicial entra como seed versionado, los preference facts y
  criterios se crean por ediciones estructuradas y el harness, el recompute se
  dispara por el mecanismo de jobs existente y la verificacion se ejecuta con
  el actor de prueba del harness, casos golden, jobs de extraccion y tests de
  dominio; la consola operativa pertenece a H6.
- La extraccion cualitativa se ejecuta en un proveedor externo gestionado con
  salida estructurada. La eleccion de proveedor especifico, despliegue y costos
  se deciden en el plan/ADR; el input enviado se limita a campos permitidos del
  listing normalizado (datos publicos de alquiler, nunca PII de usuarios ni raw
  HTML), y la spec exige el puerto, el versionado y el registro de uso, no el
  proveedor concreto.
- El idioma de extraccion es espanol (CABA); los casos golden se escriben sobre
  el dataset controlado en espanol.
- Los matcher types se registran y validan en este incremento; los evaluadores
  concretos (numeric range, categorical, geo proximity, semantic feature) son
  H3.2 y consumiran conceptos, criterios y observaciones.
- Los hard filters de H2.3 siguen siendo los unicos filtros duros; convertir
  preferencias blandas en hard filters requiere confirmacion explicita y queda
  registrado en la compilacion.
- Los preference facts de este incremento se crean por ediciones estructuradas
  y el harness; la conversion automatica de feedback a facts/propuestas es
  H3.3 (UM-H3-028).
- El reintento de extraccion cualitativa es acotado (maximo de intentos por
  registro definido en el plan); los fallos quedan consultables como
  observaciones invalidas con causa.
- Las observaciones y recomputaciones emiten eventos versionados de acuerdo con
  el diccionario de eventos (UM-H0-013), sin PII innecesaria.
- Los embeddings (UM-H3-009) y el contexto urbano (UM-H3-010) son P1: se
  especifican con su prioridad y se ordenan despues del primer recorrido
  interno del hito; no bloquean el camino critico de la beta.
- El contexto urbano usa fuentes externas con cache y limites; la incorporacion
  de señales respeta la precision geografica autorizada de cada listing.
- La verificacion de determinismo, recomputacion, lineage y eventos se ejecuta
  sobre el conjunto de prueba del harness con casos golden, de acuerdo con el
  DoD del proyecto.
