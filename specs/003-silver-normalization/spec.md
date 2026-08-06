# Feature Specification: Silver Normalization

**Feature Branch**: `003-silver-normalization`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "Especificar el hito H2.2 - Normalizacion Silver del backlog, con alcance exacto UM-H2-009 a UM-H2-018."

## Clarifications

### Session 2026-08-06

- Q: ¿Qué debe significar "estado" en la detección de cambios (FR-013) si el
  contrato de importación v1 no define ese campo? → A: La detección de cambios
  compara todos los campos normalizados presentes (precio, texto, atributos);
  "estado" se detecta únicamente cuando una versión futura del contrato lo
  incluya. No se agrega un estado inventado.
- Q: ¿Los matches exactos del dedupe determinista deben agruparse
  automáticamente en una sola property canónica? → A: Sí: los exactos
  deterministas se agrupan automáticamente en la canonical (no destructivo,
  conservando evidencia y lineage); solo los casos ambiguos quedan como
  propuestas pendientes.

## Operational Definitions

- **Listing normalizado (Silver)**: representacion persistente de una propiedad tal
  como aparece publicada en una fuente, con identidad de fuente, external id, URL,
  fecha de publicacion, ultima observacion y referencia al payload de origen en
  Bronze. Es la unidad sobre la que se construye la busqueda y el matching (H2.3).
- **Precio normalizado**: registro que conserva moneda y valor originales,
  expensas, supuestos y errores; no convierte moneda sin una tasa versionada.
- **Costo total**: suma explicita de alquiler y expensas con componentes y
  supuestos declarados, sin inventar cargos.
- **Atributo normalizado**: superficie, ambientes, dormitorios, piso, tipo,
  operacion y amenities expresados con unidades, enums y rangos validados.
- **Ubicacion normalizada**: texto original, barrio, geometria y precision
  (exact/block/barrio/aproximada/desconocida) sin inventar direccion ni
  coordenadas.
- **Geocodificacion**: resolucion de ubicaciones permitidas mediante cache, rate
  limits, adapter y fuente registrada; nunca mejora artificialmente la precision
  declarada.
- **Property canonica**: la propiedad real, separada de sus publicaciones y
  versiones, con lineage preservado a los snapshots Bronze que la produjeron.
- **Dedupe deterministico**: vinculo de matches exactos por identidad de fuente,
  hash o datos fuertes, registrando evidencia de cada vinculo; los matches exactos
  resuelven la property canonica de forma automatica sin destruir datos ni
  lineage.
- **Propuesta de dedupe (no destructiva)**: vinculo sugerido con score, evidencia
  y estado pendiente/confirmado/rechazado; los casos ambiguos no se fusionan
  automaticamente.
- **Cambio entre versiones**: deteccion de diferencias de precio, texto y
  atributos entre publicaciones de la misma propiedad, conservando before/after y
  origen; el estado se detecta solo cuando el contrato de importacion lo defina.
- **Lineage Bronze-Silver**: para cada entidad de referencia se puede volver al
  snapshot crudo y a la version de parser que la produjo.

## Review and Measurement Protocol

- La puerta de salida del hito: un operador importa propiedades (H2.1) y un
  usuario crea una busqueda, ejecuta hard filters y revisa matches persistentes
  de punta a punta (H2.3). Este incremento solo entrega la capa Silver que hace
  eso posible; la busqueda y el radar NO se evaluan aqui.
- El conjunto de prueba (fixture del harness) incluye listings validos,
  duplicados exactos, duplicados ambiguos, cambios de precio, campos faltantes,
  ubicaciones aproximadas y casos que deben ir a cuarentena (UM-H0-010). Cada
  criterio de "100%" se calcula sobre todos los casos declarados en esa fixture.
- La normalizacion se verifica comparando el resultado Silver contra el resultado
  esperado de la fixture: valores, enums, unidades, precision de ubicacion y
  referencia al payload de origen.
- El lineage se verifica recorriendo cada entidad Silver de referencia hacia su
  snapshot Bronze y su version de parser, sin pasos no registrados.
- El dedupe se verifica sobre los pares declarados: los exactos quedan vinculados
  con evidencia y resuelven la property canonica automaticamente; los ambiguos
  quedan como propuestas pendientes sin fusion.
- Los cambios entre versiones se verifican detectando la diferencia declarada
  (precio, texto o atributo; estado solo si el contrato lo define) con
  before/after y origen.
- Reimportar o reprocesar un lote con la misma identidad no debe duplicar
  entidades Silver ni inventar cambios nuevos.
- La geocodificacion (P1) se verifica sobre ubicaciones permitidas: mantiene la
  precision declarada y no excede los limites de tasa configurados.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Normalizar listings persistentes y consultables (Priority: P1)

Como persona responsable de datos, quiero que cada snapshot capturado se convierta
en un listing normalizado con precio, atributos y ubicacion confiables, para que
el radar pueda filtrar y matchear sobre datos consistentes.

**Why this priority**: Sin normalizacion Silver no hay entidades confiables sobre
las cuales aplicar hard filters ni comparar propiedades en H2.3.

**Independent Test**: El conjunto de prueba produce listings Silver con identidad
de fuente, external id, URL, publicacion, ultima observacion y referencia al
payload de origen; precio con moneda/valor originales; atributos con unidades y
enums validados; y ubicacion con texto, barrio, geometria y precision declarada.

**Acceptance Scenarios**:

1. **Given** un lote importado con registros validos, **When** se ejecuta la
   normalizacion, **Then** cada registro valido produce un listing Silver que
   conserva external id, URL, fuente, fecha de publicacion, ultima observacion y
   referencia al payload de origen.
2. **Given** un registro con precio y expensas, **When** se normaliza, **Then**
   el valor y la moneda originales se conservan tal cual, las expensas quedan
   separadas y el costo total se compone de forma explicita con sus supuestos.
3. **Given** un registro con un valor de moneda distinto al del lote sin tasa
   versionada, **When** se normaliza, **Then** no se convierte la moneda y el
   caso queda registrado como error o supuesto, nunca como conversion silenciosa.
4. **Given** un registro con atributos, **When** se normalizan, **Then** la
   superficie, ambientes, dormitorios, piso, tipo, operacion y amenities quedan
   con unidades, enums y rangos validados; los valores fuera de rango se registran
   como error o ausencia, sin coerción silenciosa.
5. **Given** un registro con direccion textual y sin coordenadas, **When** se
   normaliza, **Then** se conserva el texto original, el barrio y la precision
   desconocida, sin inventar direccion ni coordenadas.
6. **Given** un registro con coordenadas, **When** se normaliza, **Then** la
   precision se declara segun la fuente (exact/block/barrio/aproximada) y nunca
   mejor que lo que los datos soportan.

---

### User Story 2 - Separar propiedad canonica y deduplicar con evidencia (Priority: P2)

Como persona responsable de datos, quiero distinguir la propiedad real de sus
publicaciones y vincular duplicados con evidencia, para que el radar no presente
la misma propiedad dos veces ni mezcle propiedades distintas.

**Why this priority**: Sin canonical properties y dedupe trazable, un mismo
departamento publicado por dos fuentes apareceria duplicado y confundiria al
usuario; el dedupe destructivo sin evidencia esta prohibido.

**Independent Test**: Los pares exactos declarados en la fixture quedan vinculados
con evidencia y resuelven automaticamente la property canonica; los pares
ambiguos generan propuestas no destructivas en estado pendiente; cada property
canonica preserva lineage a sus publicaciones y snapshots.

**Acceptance Scenarios**:

1. **Given** dos registros de la misma fuente con identidad y contenido
   identicos, **When** se deduplica, **Then** se vinculan de forma determinista,
   quedan bajo la misma property canonica y la evidencia y el lineage se
   conservan sin fusion destructiva.
2. **Given** dos registros de fuentes distintas con datos fuertes iguales
   (external id o datos coincidentes), **When** se deduplica, **Then** se genera
   una propuesta de vinculo con score y evidencia en estado pendiente, sin
   fusionar automaticamente.
3. **Given** registros ambiguos, **When** se evalua la propuesta, **Then** el
   estado transita pendiente/confirmado/rechazado de forma auditable y el caso
   no confirmado nunca se fusiona.
4. **Given** una propiedad con multiples publicaciones y versiones, **When** se
   consulta, **Then** la property canonica se distingue de sus publicaciones y
   cada una conserva lineage a su snapshot Bronze.

---

### User Story 3 - Registrar cambios y verificar lineage (Priority: P2)

Como persona responsable de datos, quiero ver que cambio en cada version y poder
volver al dato crudo que produjo cada entidad, para auditar decisiones y explicar
datos al usuario sin afirmaciones no soportadas.

**Why this priority**: Los cambios de precio y atributos alimentan historial
(H3-031) y alertas (H5-005); el lineage completo es un guardrail de beta (100%).

**Independent Test**: Cada cambio declarado en la fixture (precio, texto o
atributo; estado cuando el contrato lo defina) queda registrado con before/after
y origen; cada entidad Silver de referencia permite volver al snapshot y parser
que la produjo.

**Acceptance Scenarios**:

1. **Given** una propiedad con una nueva publicacion que cambia el precio,
   **When** se procesa la version, **Then** el cambio queda registrado con valor
   anterior, valor nuevo y origen, sin modificar la version previa.
2. **Given** una nueva publicacion que cambia texto o atributos, **When**
   se procesa, **Then** el cambio se detecta y se conserva before/after con
   origen; un campo de estado solo se compara cuando la version del contrato lo
   defina.
3. **Given** una publicacion identica a la version vigente, **When** se procesa,
   **Then** no se registra un cambio falso ni se duplica la version.
4. **Given** una entidad Silver de referencia, **When** se recorre su lineage,
   **Then** se llega al snapshot Bronze y a la version de parser que la produjo,
   sin pasos no registrados.

### Edge Cases

- Un cambio de moneda sin tasa versionada debe registrarse como error/supuesto y
  nunca convertirse en silencio.
- Una ubicacion sin coordenadas ni barrio debe quedar con precision desconocida,
  sin coordenadas inventadas.
- Un atributo fuera de rango o con unidad ambigua debe registrarse como error o
  ausencia, no corregirse adivinando.
- Un duplicado ambiguo debe permanecer pendiente; solo los matches exactos se
  vinculan de forma determinista.
- Una correccion de datos debe crear una nueva version conservando la anterior
  (inmutabilidad), nunca sobrescribir.
- Un campo de "estado" ausente en el contrato v1 no debe generar cambios ni
  errores; se compara solo cuando una version futura del contrato lo defina.
- Un fallo de geocodificacion no debe degradar la precision declarada ni bloquear
  la normalizacion del resto.
- Reprocesar el mismo conjunto de snapshots no debe duplicar entidades Silver ni
  generar cambios falsos.
- Un lote reimportado con la misma identidad (H2.1) no debe producir entidades
  Silver nuevas.
- Un vinculo de dedupe no debe poder borrar datos de origen ni fusionar casos
  ambiguos; el agrupamiento automatico aplica solo a matches exactos
  deterministas y conserva evidencia y lineage.

## Requirements *(mandatory)*

### Functional Requirements

#### Fuentes y versiones

- **FR-001**: El sistema MUST normalizar cada snapshot capturado en un listing
  Silver que conserve identidad de fuente, external id, URL, fecha de publicacion,
  ultima observacion y referencia al payload de origen.
- **FR-002**: La identidad de la fuente y la version del formato MUST
  conservarse en cada entidad Silver y MUST ser trazables al run y snapshot de
  origen.

#### Precio y costo total

- **FR-003**: La normalizacion de precio MUST preservar la moneda y el valor
  originales, las expensas, los supuestos y los errores; MUST NO convertir moneda
  sin una tasa versionada.
- **FR-004**: El costo total MUST componerse de forma explicita (alquiler y
  expensas) con componentes y supuestos declarados y consultables.

#### Atributos inmobiliarios

- **FR-005**: Los atributos normalizados MUST usar unidades, enums y rangos
  validados (superficie, ambientes, dormitorios, piso, tipo, operacion y
  amenities).
- **FR-006**: Un valor de atributo invalido o fuera de rango MUST registrarse
  como error o ausencia normalizada; MUST NO corregirse adivinando ni aplicarse
  coerción.

#### Ubicacion y granularidad

- **FR-007**: La ubicacion normalizada MUST conservar texto original, barrio,
  geometria y precision (exact/block/barrio/aproximada/desconocida) y MUST NO
  inventar direccion ni coordenadas.
- **FR-008**: La geocodificacion (P1) MUST usar cache, rate limits, un adapter y
  una fuente registrada, y MUST NO mejorar la precision mas alla de lo que los
  datos soportan. Depende de FR-007.

#### Property canonica y dedupe

- **FR-009**: El sistema MUST separar la property canonica de sus publicaciones y
  versiones, preservando lineage a los snapshots Bronze.
- **FR-010**: Cada publicacion/version MUST ser inmutable; una correccion MUST
  crear una nueva version conservando la anterior.
- **FR-011**: El dedupe deterministico MUST vincular matches exactos por identidad
  de fuente, hash o datos fuertes, registrando evidencia de cada vinculo, y MUST
  agrupar esos matches en una unica property canonica de forma automatica sin
  destruir datos ni lineage.
- **FR-012**: Los casos ambiguos MUST generar propuestas no destructivas con
  score, evidencia y estado pendiente/confirmado/rechazado; MUST NO fusionar
  automaticamente casos ambiguos.

#### Cambios entre versiones

- **FR-013**: El sistema MUST detectar y registrar cambios entre versiones
  (precio, texto y atributos normalizados) conservando before/after y origen; un
  campo de estado MUST compararse solo cuando la version del contrato de
  importacion lo defina.

#### Lineage

- **FR-014**: Para cada entidad Silver de referencia, el sistema MUST permitir
  volver al snapshot Bronze y a la version de parser que la produjo, sin pasos no
  registrados.

### Key Entities

- **Listing Silver**: publicacion normalizada con identidad de fuente, external
  id, URL, publicacion, ultima observacion y referencia al payload de origen.
- **Precio Normalizado**: moneda/valor originales, expensas, supuestos y errores;
  conversion solo con tasa versionada.
- **Atributos Normalizados**: superficie, ambientes, dormitorios, piso, tipo,
  operacion y amenities con unidades/enums/rangos validados.
- **Ubicacion Normalizada**: texto original, barrio, geometria y precision
  declarada.
- **Property Canonica**: propiedad real separada de sus publicaciones y versiones,
  con lineage a Bronze.
- **Publicacion/Versiones**: representaciones inmutables de una propiedad en una
  fuente en un momento dado.
- **Dedupe Link**: vinculo determinista con evidencia registrada.
- **Dedupe Proposal**: propuesta no destructiva con score, evidencia y estado
  pendiente/confirmado/rechazado.
- **Change Record**: cambio detectado entre versiones con before/after y origen.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Normalizar listings | UM-H2-009 a UM-H2-012 |
| User Story 2 - Canonical properties y dedupe | UM-H2-014, UM-H2-015, UM-H2-016 |
| User Story 3 - Cambios y lineage | UM-H2-017, UM-H2-018 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H2-009 | FR-001, FR-002 | US1.1, SC-001 y SC-007 |
| UM-H2-010 | FR-003, FR-004 | US1.2-US1.3, SC-003 |
| UM-H2-011 | FR-005, FR-006 | US1.4, SC-002 |
| UM-H2-012 | FR-007 | US1.5-US1.6, SC-006 |
| UM-H2-013 | FR-008 | US1.6, SC-006 |
| UM-H2-014 | FR-009, FR-010 | US2.4, SC-008 |
| UM-H2-015 | FR-011 | US2.1, SC-004 |
| UM-H2-016 | FR-012 | US2.2-US2.3, SC-004 |
| UM-H2-017 | FR-013 | US3.1-US3.3, SC-005 |
| UM-H2-018 | FR-014 | US3.4, SC-007 |

## Constitution Alignment *(mandatory)*

- **Persistent product objects**: listings Silver, properties canonicas,
  versiones, dedupe links, propuestas y cambios son objetos persistentes e
  inmutables; nada vive solo en logs o memoria. Esto habilita matches persistentes
  (H2.3) sin depender del chat.
- **Evidence and audit needs**: cada entidad conserva fuente, version, run,
  snapshot de origen y evidencia de dedupe; los cambios conservan before/after y
  origen, y toda entidad permite volver a su snapshot y parser. Sustenta el
  guardrail de lineage completo (100%).
- **LLM boundary**: no se incorpora un LLM en este incremento. Normalizacion,
  dedupe, deteccion de cambios y geocodificacion son codigo determinista,
  versionado y testeable.
- **Verification approach**: comparacion contra el resultado esperado del
  conjunto de prueba, casos golden de dedupe (exactos vs ambiguos), verificacion
  de before/after, recorrido de lineage hasta Bronze y pruebas de idempotencia del
  reprocesamiento.
- **Dependency direction**: la normalizacion consume snapshots Bronze a traves de
  puertos del dominio; la geocodificacion es un adapter con fuente registrada;
  ninguna capa Silver depende de FastAPI, DB, LLM ni UI. El dedupe nunca es
  destructivo sin evidencia y confianza.
- **Minimal change**: el incremento se limita a la capa Silver (UM-H2-009 a
  UM-H2-018) y excluye search profiles, hard filters, matching y radar (H2.3),
  features Gold y superficies de usuario final.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los listings del conjunto de prueba alcanza una entidad
  Silver que conserva external id, URL, fuente, publicacion, ultima observacion y
  referencia al payload de origen.
- **SC-002**: El 100% de los atributos del conjunto de prueba queda con unidades,
  enums y rangos validados; el 0% de los valores invalidos se corrige adivinando.
- **SC-003**: El 100% de los precios del conjunto de prueba conserva moneda y
  valor originales; 0 conversiones de moneda sin tasa versionada.
- **SC-004**: El 100% de los pares duplicados exactos declarados queda vinculado
  con evidencia registrada y agrupado en su property canonica; el 0% de los pares
  ambiguos se fusiona automaticamente.
- **SC-005**: El 100% de los cambios declarados en el conjunto de prueba (precio,
  texto o atributos; estado solo si el contrato lo define) queda registrado con
  before/after y origen.
- **SC-006**: El 100% de las ubicaciones geocodificables mantiene la precision
  declarada y el 0% de los casos supera los limites de tasa configurados; el 0% de
  los listings de prueba contiene direcciones o coordenadas inventadas.
- **SC-007**: El 100% de las entidades Silver de referencia permite volver al
  snapshot Bronze y a la version de parser que la produjo.
- **SC-008**: Reprocesar el conjunto de prueba produce 0 entidades Silver
  duplicadas, 0 versiones modificadas retroactivamente y 0 cambios falsos
  respecto del primer procesamiento.

## Assumptions

- El alcance incluye exactamente UM-H2-009 a UM-H2-018 (Epica H2.2 -
  Normalizacion Silver). La busqueda, el matching y el radar pertenecen a H2.3.
- Los snapshots Bronze, los runs y la cuarentena del incremento
  `bronze-ingestion` (H2.1) ya estan disponibles como entrada de la
  normalizacion.
- No se convierte moneda en este incremento: sin una tasa versionada, el caso se
  registra como error o supuesto. La decision de incorporar tasas queda fuera de
  alcance.
- El conjunto de prueba se define con casos validos, duplicados exactos y
  ambiguos, cambios de precio, campos faltantes, ubicaciones aproximadas y casos
  de cuarentena, de acuerdo con UM-H0-010.
- La geocodificacion (UM-H2-013) es P1: la base de este incremento (UM-H2-012)
  conserva texto, barrio, geometria y precision sin geocodificar. La eleccion del
  proveedor de geocodificacion se registra en el plan, no en esta spec.
- El reprocesamiento se comporta de forma idempotente sobre el mismo conjunto de
  snapshots; cambios de parser crean nuevas versiones conservando las usadas
  previamente, en linea con UM-H6-004.
- La revision/confirmacion visual de propuestas de dedupe es posterior a este
  incremento; aqui las propuestas son consultables por estado
  (pendiente/confirmado/rechazado) sin superficie de usuario final.
- No se construyen features Gold, historial de precio visible al usuario ni
  notificaciones en este incremento.
