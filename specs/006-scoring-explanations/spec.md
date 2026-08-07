# Feature Specification: Scoring and Explanations

**Feature Branch**: `006-scoring-explanations`

**Created**: 2026-08-07

**Status**: Draft

**Input**: User description: "Arranquemos con la especificacion de la epica H3.2 - Scoring y explicaciones del backlog, con alcance exacto UM-H3-012 a UM-H3-022."

## Clarifications

### Session 2026-08-07

- Q: ¿Incluimos en esta v1 la redaccion generativa (LLM) de las explicaciones,
  o usamos solo copy determinista derivado del desglose? → A: Solo copy
  determinista por templates derivado del desglose; sin LLM en v1. La
  redaccion generativa (UM-H3-018) queda fuera del incremento y, si se
  incorpora en un incremento posterior, debera no agregar hechos y referenciar
  versiones inmutables.
- Q: Cuando un recompute de observaciones (H3.1) o una reimportacion cambian
  los datos subyacentes, ¿que pasa con los runs ya publicados del radar en este
  incremento? → A: Los runs congelados siguen vigentes: solo los triggers
  existentes (editar/reanudar perfil, importacion) crean runs nuevos; sin
  invalidacion automatica en H3.2. El recalculado automatico tras cambios
  relevantes es H3.3 (UM-H3-030).
- Q: Cuando un radar muestra un run publicado con el scoring baseline de H2.3
  (sin explicaciones ni desglose), ¿que debe ver el usuario? → A: El run
  legacy se muestra como hoy, con score sin desglose y un aviso de que la
  explicacion no esta disponible para ese run; sin migracion ni backfill; se
  reemplaza naturalmente cuando un trigger existente genera el primer run v1.
- Q: ¿Que dimensiones debe mostrar la matriz del comparador? → A: Mixto:
  dimensiones fijas basicas (precio total, expensas, superficie, ambientes,
  dormitorios, ubicacion/precision, score con confianza) mas los criterios
  activos del perfil con su evaluacion, evidencia y estado faltante.

Las decisiones por default (limite de comparacion, contratos HTTP en alcance,
shortlist compartida con H3.3, escala de score normalizada 0..1 heredada de
H2.3) estan documentadas en [Assumptions](#assumptions).

## Operational Definitions

- **Scoring policy v1**: conjunto versionado e inmutable que fija que criterios
  participan, sus pesos, la normalizacion, los gates (umbrales que pueden
  excluir o capar), la politica de confianza, los bonuses, las penalizaciones y
  los tie-breaks. Es la unica autoridad sobre como se combina un perfil con un
  listing en scoring v1.
- **Evaluador generico**: componente evaluable que comparte un contrato pequeno
  (entrada: criterio ejecutable + observaciones/datos del listing; salida:
  score, confianza y evidencia). Tipos iniciales: numeric range, categorical,
  geo proximity y semantic feature.
- **Criterion evaluation**: resultado persistido de evaluar un criterio contra
  un listing dentro de un run: referencia al criterio (versionado), inputs
  usados (versionados), contribucion al score total y razon textual determinista
  que alimenta la explicacion.
- **Desconocido vs evidencia negativa**: la falta de datos para evaluar un
  criterio (desconocido) baja la confianza de la evaluacion pero NO equivale a
  un mismatch observado (evidencia negativa). Ambas deben tratarse y mostrarse
  de forma distinguible.
- **Feature snapshot**: copia congelada de las observaciones y datos del listing
  (o de su version de features) usada por un run; garantiza que la explicacion
  se reconstruya sobre lo mismo que se puntuo.
- **Profile snapshot**: copia congelada del perfil/busqueda (criterios
  ejecutables, policy version) usada por un run; la misma politica que H2.3.
- **Recommendation run (v1)**: ejecucion atomica de scoring que congela profile
  snapshot, feature snapshots, candidate set, policy version y score version, y
  publica un orden y desglose. Un run fallido no reemplaza al ultimo run valido
  y registra la causa. Los runs publicados siguen vigentes hasta que un trigger
  existente (editar/reanudar perfil, importacion) genere un run nuevo: un
  cambio de observaciones o datos Silver no los invalida en este incremento.
- **Explicacion**: desglose generado desde el breakdown del run: razones
  (criterios con contribucion y evidencia), riesgos (confianza baja o datos
  faltantes relevantes), datos faltantes y confianza global. El copy se
  produce con templates deterministas desde el desglose; la v1 no usa
  redaccion generativa.
- **Evidence ref**: referencia interna a la evidencia persistida (observacion,
  fragmento, regla/modelo y version, o dato del listing) que soporta una razon.
- **Comparacion estructurada**: vista que compara hasta el limite definido de
  listings usando dimensiones homogeneas (mismas unidades y fuentes de valor),
  muestra los datos faltantes por celda y explicita tradeoffs; no inventa un
  ganador. Las dimensiones se componen de fijas basicas (precio total,
  expensas, superficie, ambientes, dormitorios, ubicacion/precision, score con
  confianza) y de los criterios activos del perfil con su evaluacion y
  evidencia.
- **Shortlist de comparacion**: seleccion persistida de listings del mismo radar
  para comparar, con alcance por busqueda; las vistas de producto de shortlist
  y descartados con feedback son H3.3.
- **Score version**: identificador inmutable de la version de policy + evaluadores
  que produjo un run; toda superficie que muestra un score referencia su version.

## Review and Measurement Protocol

- La puerta de salida del hito: cada recomendacion se reconstruye desde perfil,
  listing, features, scoring y evidencia. Este incremento entrega policy,
  evaluadores, evaluaciones, scoring deterministico, runs atomicos,
  explicaciones, comparacion estructurada y su superficie web. El feedback
  (H3.3), el dataset golden y las regresiones (H3.4), el chat (H4) y las
  alertas (H5) NO se evaluan aqui.
- La scoring policy se verifica con casos golden de registro y edicion: cada
  cambio produce una version inmutable, y las policies con pesos no
  normalizables, gates no soportados o referencias a criterios inexistentes se
  rechazan sin persistir datos parciales.
- Los evaluadores genericos se verifican con casos golden por tipo (numeric
  range, categorical, geo proximity, semantic feature): entrada, score,
  confianza y evidencia esperados; todos comparten el mismo contrato de salida.
- La distincion desconocido vs evidencia negativa se verifica con casos golden:
  falta de datos baja confianza, no puntua como mismatch, y ambos estados se
  serializan de forma distinguible.
- El scoring deterministico se verifica ejecutando dos veces la misma entrada
  (mismo profile snapshot, feature snapshots, candidate set y policy): el orden
  y el desglose son identicos y 0 invocaciones realizan llamadas a red,
  almacenamiento o modelo externo.
- Las evaluaciones de criterio se verifican confirmando que el 100% persiste
  criterio, inputs, contribucion y razon con sus versiones, y que ninguna vista
  de resultados usa evaluaciones de un run no publicado.
- Los runs atomicos se verifican induciendo un fallo a mitad de un run: el run
  fallido queda con causa registrada, no reemplaza al ultimo valido y no deja
  resultados parciales visibles. Tambien se verifica que un cambio de
  observaciones o de datos Silver no invalida ni re-ejecuta runs publicados:
  la vista sigue al ultimo run valido hasta un trigger existente.
- El recalculado automatico tras cambios de perfil, feedback u observaciones
  (UM-H3-030) es H3.3 y NO se evalua en este incremento.
- Las explicaciones se verifican confirmando que el 100% de las razones tiene
  evidence refs internas, que riesgos y datos faltantes derivan del breakdown,
  que 0 afirmaciones se sostienen sin evidencia interna, y que el copy es
  determinista (doble ejecucion del mismo desglose produce el mismo texto).
- La comparacion estructurada se verifica con casos dentro y fuera del limite,
  de distintas busquedas y con datos faltantes: se respeta el limite, se
  muestran los faltantes y 0 comparaciones inventan un ganador.
- La superficie web se verifica con tests de componente y revision de
  accesibilidad/copy por convencion del proyecto: cards y detalle distinguen
  evidencia fuerte/media/baja y desconocidos, ninguna superficie presenta
  scores como certeza, y los runs legacy del baseline de H2.3 se muestran sin
  desglose con aviso de explicacion no disponible (0 razones fabricadas).
- La instrumentacion se verifica confirmando que runs, evaluaciones y vistas de
  explicacion/comparacion emiten sus eventos versionados sin PII innecesaria.
- El comparador persistente (P1) se verifica confirmando que la shortlist
  sobrevive recarga, respeta el limite, pertenece al radar y muestra una matriz
  responsive con dimensiones auditables.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Definir la scoring policy v1 versionada (Priority: P0)

Como equipo de producto y datos, quiero una scoring policy versionada e
inmutable que fije criterios, pesos, normalizacion, gates, confianza, bonuses,
penalizaciones y tie-breaks, para que el ranking sea consistente, explicable y
reproducible en el tiempo.

**Why this priority**: Es la autoridad unica del ranking; sin version inmutable,
dos runs o dos vistas no podrian responder a la misma definicion y la
explicabilidad perderia base.

**Independent Test**: El conjunto de prueba registra y edita policies y
verifica que cada cambio produce una version nueva, y que policies invalidas se
rechazan sin persistir datos parciales.

**Acceptance Scenarios**:

1. **Given** una scoring policy con criterios, pesos, normalizacion, gates,
   politica de confianza, bonuses, penalizaciones y tie-breaks, **When** se
   registra, **Then** queda persistida con su version inmutable y es consultable
   por numero de version.
2. **Given** una policy existente, **When** se edita, **Then** se crea una
   version nueva y la anterior queda intacta y consultable.
3. **Given** una policy con pesos que no normalizan, gates no soportados o
   referencias a criterios inexistentes, **When** se registra o edita, **Then**
   se rechaza con un error accionable sin persistir datos parciales.
4. **Given** un run publicado, **When** cambia la policy, **Then** el run
   conserva su version de policy y los resultados nuevos usan la version nueva
   sin mezclar versiones en una misma vista.

---

### User Story 2 - Evaluar con evaluadores genericos (Priority: P0)

Como motor de matching, quiero evaluadores genericos (numeric range,
categorical, geo proximity y semantic feature) que compartan un contrato
pequeno y devuelvan score, confianza y evidencia, para que cada tipo de
criterio se evalue con el mismo patron y el desglose sea uniforme.

**Why this priority**: Es la capa que traduce criterios ejecutables (H3.1) en
contribuciones con evidencia; sin contrato comun, el scoring y las
explicaciones no podrian componerse.

**Independent Test**: El conjunto de prueba ejecuta casos golden por tipo de
evaluador y verifica score, confianza y evidencia esperados bajo el mismo
contrato de salida.

**Acceptance Scenarios**:

1. **Given** un criterio numeric range y las observaciones del listing, **When**
   se evalua, **Then** se produce score, confianza y evidencia dentro del
   contrato comun.
2. **Given** un criterio categorical, geo proximity o semantic feature y sus
   datos, **When** se evalua, **Then** el resultado sigue el mismo contrato de
   salida que numeric range.
3. **Given** un evaluador con datos insuficientes, **When** se ejecuta, **Then**
   retorna confianza baja con estado desconocido explicito y evidencia ausente,
   sin inventar un puntaje.
4. **Given** un tipo de evaluador no soportado por la policy, **When** se
   invoca, **Then** la evaluacion se rechaza con error accionable.

---

### User Story 3 - Distinguir desconocido de evidencia negativa (Priority: P0)

Como usuario del radar, quiero que la falta de datos se trate y se muestre
distinto de un mismatch observado, para no penalizar ni asustar con informacion
que el sistema no tiene.

**Why this priority**: Es la diferencia entre "no lo sabemos" y "no
matchea"; confundirlos degrada tanto el ranking como la confianza en las
razones.

**Independent Test**: El conjunto de prueba ejecuta casos golden de desconocido
y de mismatch y verifica que ambos estados se serializan y puntuan de forma
distinguible.

**Acceptance Scenarios**:

1. **Given** un criterio sin datos para evaluarlo, **When** se evalua, **Then**
   el resultado declara desconocido con confianza baja y 0 penalizacion de
   mismatch.
2. **Given** un criterio con datos que no satisfacen el requisito, **When** se
   evalua, **Then** el resultado declara evidencia negativa con su contribucion
   y evidencia correspondiente.
3. **Given** una explicacion con desconocidos y mismatches, **When** se
   muestra, **Then** ambos estados se presentan en secciones o textos
   distinguibles.

---

### User Story 4 - Evaluar criterios y calcular scoring v1 deterministico (Priority: P0)

Como equipo de producto, quiero que el scoring v1 sea puro y deterministico:
la misma entrada produce el mismo orden y desglose sin llamadas a red, DB o
LLM, y cada evaluacion quede persistida con inputs, contribucion y razon.

**Why this priority**: Es el corazon del matching auditable: si el scoring no es
reproducible, la explicacion y las regresiones posteriores (H3.4) no tienen
sentido.

**Independent Test**: El conjunto de prueba ejecuta el scoring dos veces sobre
la misma entrada y verifica orden y desglose identicos, y que las evaluaciones
persisten con criterio, inputs, contribucion y razon versionados.

**Acceptance Scenarios**:

1. **Given** un profile snapshot, feature snapshots, candidate set y policy,
   **When** se ejecuta el scoring v1, **Then** el orden y el desglose son
   identicos entre ejecuciones de la misma entrada.
2. **Given** una evaluacion de criterio, **When** se persiste, **Then** queda
   con criterio, inputs usados, contribucion y razon, todos con sus versiones.
3. **Given** la ejecucion del scoring, **When** se audita, **Then** 0
   invocaciones dependen de red, almacenamiento o modelo externo para producir
   el orden.
4. **Given** evaluaciones de un run no publicado, **When** un consumidor pide
   resultados, **Then** no se usan en vistas de resultados.

---

### User Story 5 - Publicar recommendation runs atomicos (Priority: P0)

Como equipo de operacion y producto, quiero que los runs de recomendacion se
publiquen atomicamente: un run fallido no reemplaza al ultimo valido y registra
la causa, para que el usuario nunca vea resultados parciales ni regresiones no
explicadas.

**Why this priority**: La confianza del radar depende de que el estado publicado
siempre corresponda a un run completo y versionado.

**Independent Test**: El conjunto de prueba induce un fallo a mitad de un run y
verifica que el ultimo run valido permanece publicado, que el fallido registra
causa y que no hay resultados parciales visibles.

**Acceptance Scenarios**:

1. **Given** un run en ejecucion, **When** falla a mitad, **Then** queda con
   causa registrada y el ultimo run valido sigue siendo el publicado.
2. **Given** un run exitoso, **When** se publica, **Then** congela profile
   snapshot, feature snapshots, candidate set, policy version y score version
   antes de exponer resultados.
3. **Given** un run fallido, **When** se consulta el estado, **Then** el fallo
   queda consultable con su causa y 0 resultados parciales se exponen.
4. **Given** un cambio de observaciones o datos Silver posterior a un run,
   **When** se consulta el radar, **Then** el ultimo run valido sigue vigente
   hasta que un trigger existente genere un run nuevo; 0 invalidacion o
   re-ejecucion automatica en este incremento.

---

### User Story 6 - Explicar recomendaciones desde evidencia (Priority: P0)

Como usuario del radar, quiero razones, riesgos, datos faltantes y confianza
derivados del desglose del run, para entender por que algo matchea sin creer
afirmaciones sin soporte.

**Why this priority**: Es la explicabilidad del producto: la razon debe poder
seguirse hasta la evidencia persistida (UM-H3-001 a UM-H3-011) o declararse
como desconocida.

**Independent Test**: El conjunto de prueba genera explicaciones y verifica que
el 100% de las razones cita evidence refs internas, que riesgos y faltantes
derivan del breakdown, que 0 afirmaciones fuera del desglose se agregan y que
el copy es determinista por templates.

**Acceptance Scenarios**:

1. **Given** un run publicado, **When** se genera la explicacion de un listing,
   **Then** se producen razones con contribucion y evidence refs, riesgos,
   datos faltantes y confianza global desde el desglose.
2. **Given** una razon, **When** se audita, **Then** referencia evidencia
   interna persistida (observacion, fragmento, fuente y version) o declara
   desconocido.
3. **Given** el desglose de un run, **When** se genera el copy de la
   explicacion, **Then** se produce con templates deterministas: dos
   generaciones del mismo desglose producen el mismo texto y 0 afirmaciones
   fuera del desglose se agregan.
4. **Given** un criterio con confianza baja, **When** se muestra la explicacion,
   **Then** el riesgo y el faltante asociados se declaran explicitamente.

---

### User Story 7 - Exponer la explicacion por listing y por busqueda (Priority: P0)

Como aplicacion (Product API) y web, quiero consultar la explicacion de un
listing dentro de un run autorizado y la lista de explicaciones de una busqueda,
con score version, profile snapshot, feature snapshot, criterios y evidence
refs y permisos deny-by-default.

**Why this priority**: Sin contrato expuesto con ownership, ni el detalle ni las
cards pueden mostrar razones consistentes con lo persistido.

**Independent Test**: El conjunto de prueba consulta explicaciones por listing y
por busqueda y verifica contenido completo, errores tipados y denegacion de
accesos cruzados.

**Acceptance Scenarios**:

1. **Given** una busqueda con un run publicado, **When** se consulta la
   explicacion por listing, **Then** se devuelve score version, profile
   snapshot, feature snapshot, criterios y evidence refs con sus versiones.
2. **Given** una busqueda con un run publicado, **When** se consulta la lista de
   explicaciones, **Then** cada item incluye score, razones y datos faltantes
   del mismo run, sin mezclar versiones de policy.
3. **Given** un listing que no pertenece a los runs de la busqueda, **When** se
   consulta su explicacion, **Then** se deniega con error tipado (no encontrado
   o no autorizado) y 0 datos se filtran.
4. **Given** una busqueda ajena al usuario, **When** se consulta, **Then** se
   deniega con deny-by-default sin revelar existencia.

---

### User Story 8 - Comparar listings de forma estructurada (Priority: P0)

Como usuario del radar, quiero comparar hasta el limite definido de listings del
mismo radar con dimensiones homogeneas, datos faltantes y tradeoffs, para
decidir sin que el sistema invente un ganador.

**Why this priority**: La comparacion es decision de producto clave de H3; un
"ganador" generativo sin desglose violaria la politica de evidencia.

**Independent Test**: El conjunto de prueba compara casos dentro y fuera del
limite, de distintas busquedas y con faltantes, y verifica limite, dimensiones
homogeneas, faltantes visibles y 0 ganadores inventados.

**Acceptance Scenarios**:

1. **Given** hasta el limite de listings del mismo radar, **When** se comparan,
   **Then** se produce una matriz con dimensiones homogeneas (mismas unidades y
   fuentes de valor).
2. **Given** una celda sin datos, **When** se compara, **Then** se muestra como
   faltante y 0 como valor negativo o mismatch.
3. **Given** mas listings que el limite definido, **When** se compara, **Then**
   la operacion se rechaza con un error accionable que indica el limite.
4. **Given** listings de busquedas distintas, **When** se compara, **Then** la
   operacion se rechaza con deny-by-default.
5. **Given** una comparacion, **When** se presenta, **Then** 0 afirmaciones de
   ganador se generan; los tradeoffs se explicitan con la evidencia de cada
   celda.
6. **Given** la matriz de comparacion, **When** se muestra, **Then** las
   dimensiones incluyen las fijas basicas y los criterios activos del perfil,
   cada uno con su valor, evidencia y estado faltante.

---

### User Story 9 - Mostrar razones, riesgos e incertidumbre en la web (Priority: P0)

Como usuario del radar, quiero que cards y detalle distingan evidencia
fuerte/media/baja, desconocidos y filtros cumplidos, sin presentar scores como
certeza, para decidir con honestidad sobre la informacion disponible.

**Why this priority**: La confianza en el radar se juega en como se presenta la
incertidumbre; ocultar desconocidos o pintar scores como verdades destruye la
propuesta de valor.

**Independent Test**: La revision de componente, accesibilidad y copy verifica
que cards y detalle distinguen niveles de evidencia y desconocidos, y que 0
superficies presentan scores como certeza.

**Acceptance Scenarios**:

1. **Given** un listing con explicacion, **When** se muestra la card, **Then**
   se ven razones con nivel de evidencia distinguible (fuerte/media/baja) y
   estado de filtros cumplidos.
2. **Given** un listing con datos faltantes o confianza baja, **When** se muestra
   el detalle, **Then** los riesgos y desconocidos se presentan en seccion o
   copy distinguible de los mismatches.
3. **Given** cualquier superficie con score, **When** se muestra, **Then** el
   score se presenta como indicador con su nivel de confianza y 0 copy afirma
   certeza o valor absoluto de "verdad".
4. **Given** la carga de una explicacion, **When** falla o tarda, **Then** se
   muestran estados de carga, error recuperable y vacio distinguibles (sin
   mostrar datos ajenos).
5. **Given** un run publicado con el scoring baseline de H2.3 (legacy), **When**
   se muestra el radar, **Then** el score se muestra sin desglose con un aviso
   de que la explicacion no esta disponible para ese run; 0 razones fabricadas.

---

### User Story 10 - Construir el comparador persistente (Priority: P1)

Como usuario del radar, quiero seleccionar listings del mismo radar, conservar
la shortlist y ver una matriz responsive con dimensiones auditables, para
decidir entre candidatos con calma.

**Why this priority**: Es P1 del backlog: completa la comparacion con superficie
de producto, pero no bloquea el camino critico de la beta.

**Independent Test**: El conjunto de prueba verifica que la shortlist persiste
por busqueda, respeta el limite, sobrevive recarga y que la matriz es usable en
desktop/mobile con dimensiones auditables.

**Acceptance Scenarios**:

1. **Given** listings del mismo radar, **When** se seleccionan hasta el limite,
   **Then** quedan en una shortlist persistente por busqueda que sobrevive
   recarga y navegacion.
2. **Given** la shortlist, **When** se abre el comparador, **Then** se muestra
   una matriz responsive donde cada dimension muestra valor, evidencia y
   faltante.
3. **Given** una celda o fila de la matriz, **When** se explora, **Then** se
   puede navegar al detalle del listing correspondiente.
4. **Given** una shortlist que excede el limite, **When** se agrega un listing,
   **Then** la accion se rechaza con indicacion del limite.

### Edge Cases

- Una policy con pesos no normalizables, gates no soportados o criterios
  inexistentes se rechaza al versionar; no se persiste a medias.
- Una policy editada nunca altera los runs que la usaron: cada vista usa una
  sola version de policy.
- Un evaluador sin datos retorna desconocido con confianza baja, no un puntaje
  inventado.
- Desconocido y evidencia negativa nunca se serializan ni se muestran igual.
- Un run fallido a mitad no publica resultados parciales ni reemplaza al ultimo
  valido.
- Un cambio de observaciones o datos Silver no invalida ni re-ejecuta runs
  publicados en este incremento: la vista sigue al ultimo run valido hasta un
  trigger existente; el recalculado automatico tras cambios relevantes
  (UM-H3-030) es H3.3.
- Una explicacion nunca cita evidencia de otro run, otra busqueda u otro
  usuario.
- El copy de explicacion es determinista por templates: 0 variacion entre
  ejecuciones de la misma entrada y 0 afirmaciones fuera del desglose.
- Una consulta de explicacion de un listing fuera del candidate set del run se
  deniega; 0 datos se filtran.
- Una comparacion con listings de busquedas distintas se rechaza; 0 datos de
  otra busqueda se mezclan.
- Una comparacion que excede el limite se rechaza con mensaje accionable.
- La matriz del comparador incluye solo dimensiones fijas basicas y criterios
  activos del perfil: 0 criterios inactivos o de otra busqueda se muestran como
  dimensiones.
- Las celdas sin datos de una comparacion se muestran como faltantes, no como
  valores negativos.
- La UI nunca presenta scores como certeza ni mezcla scores de distintas
  versiones de policy en una misma vista.
- La UI distingue estados de carga, error recuperable, vacio y no autorizado.
- La shortlist del comparador pertenece a su busqueda y a su usuario; no hay
  shortlists compartidas entre radares.
- Este incremento no expone consola operativa de scoring (H6): el operador no
  tiene superficie sobre runs ni explicaciones de usuarios; la verificacion usa
  el actor de prueba del harness y los contratos de Product API de H3.2.

## Requirements *(mandatory)*

### Functional Requirements

#### Scoring policy

- **FR-001**: El sistema MUST soportar registrar scoring policies versionadas e
  inmutables que fijen criterios participantes, pesos, normalizacion, gates,
  politica de confianza, bonuses, penalizaciones y tie-breaks; cada cambio MUST
  producir una version nueva sin modificar versiones previas.
- **FR-002**: Las policies invalidas (pesos no normalizables, gates no
  soportados, criterios inexistentes o evaluadores no soportados) MUST
  rechazarse con error accionable sin persistir datos parciales.
- **FR-003**: Cada run y cada superficie con score MUST referenciar la version
  de policy que lo produjo; una misma vista MUST NO mezclar scores de
  versiones distintas.

#### Evaluadores genericos

- **FR-004**: Los evaluadores genericos iniciales (numeric range, categorical,
  geo proximity y semantic feature) MUST compartir un contrato de salida comun:
  score, confianza y evidencia, y MUST retornar esos tres componentes en toda
  evaluacion.
- **FR-005**: Un evaluador con datos insuficientes MUST retornar estado
  desconocido con confianza baja y evidencia ausente, sin inventar puntaje ni
  mismatch.

#### Desconocido vs evidencia negativa

- **FR-006**: El scoring MUST tratar la falta de datos (desconocido) de forma
  distinguible del mismatch observado (evidencia negativa): el desconocido
  baja confianza y MUST NO puntuar como mismatch; ambos estados MUST
  serializarse y mostrarse de forma distinguible.

#### Evaluaciones y scoring deterministico

- **FR-007**: Cada evaluacion de criterio contra un listing dentro de un run
  MUST persistirse con criterio, inputs usados, contribucion y razon, todos con
  sus versiones.
- **FR-008**: El calculo del scoring v1 MUST ser puro y deterministico: la
  misma entrada (profile snapshot, feature snapshots, candidate set y policy)
  MUST producir el mismo orden y desglose, sin llamadas a red, almacenamiento o
  modelo externo.
- **FR-009**: Las evaluaciones y resultados de runs no publicados MUST NO usarse
  en vistas de resultados.

#### Runs atomicos

- **FR-010**: Un run MUST congelar profile snapshot, feature snapshots, candidate
  set, policy version y score version antes de publicar resultados, y MUST
  publicarse atomicamente. Un cambio de observaciones o datos Silver posterior
  MUST NO invalidar ni re-ejecutar runs publicados en este incremento: la vista
  de resultados MUST seguir al ultimo run valido hasta que un trigger existente
  (edicion/reanudacion de perfil, importacion) genere un run nuevo; el
  recalculado automatico tras cambios relevantes (UM-H3-030) es H3.3.
- **FR-011**: Un run fallido MUST NO reemplazar al ultimo run valido, MUST NO
  exponer resultados parciales y MUST registrar la causa del fallo.

#### Explicaciones y contratos

- **FR-012**: Las explicaciones MUST generarse desde el desglose del run:
  razones con contribucion y evidence refs, riesgos, datos faltantes y
  confianza global.
- **FR-013**: Cada razon MUST referenciar evidencia interna persistida
  (observacion, fragmento, fuente y version) o declarar desconocido; el copy de
  explicacion MUST generarse con templates deterministas desde el desglose, sin
  redaccion generativa en v1, y 0 afirmaciones sin evidencia interna MUST
  publicarse.
- **FR-014**: La explicacion por listing y por busqueda MUST exponerse con score
  version, profile snapshot, feature snapshot, criterios y evidence refs, con
  permisos deny-by-default y errores tipados (no encontrado / no autorizado /
  validacion).
- **FR-015**: Las consultas de explicacion MUST respetar ownership: listings o
  runs ajenos a la busqueda o al usuario MUST denegarse sin filtrar datos.

#### Comparacion estructurada

- **FR-016**: La comparacion estructurada MUST limitarse al maximo de listings
  definido por la politica, MUST usar dimensiones homogeneas (mismas unidades y
  fuentes de valor), MUST mostrar los datos faltantes por celda y MUST NO
  inventar un ganador. Las dimensiones MUST componerse de las fijas basicas
  (precio total, expensas, superficie, ambientes, dormitorios,
  ubicacion/precision, score con confianza) y de los criterios activos del
  perfil con su evaluacion y evidencia.
- **FR-017**: Las comparaciones MUST limitarse a listings del mismo radar; inputs
  de otras busquedas MUST rechazarse con deny-by-default.

#### Superficie web

- **FR-018**: Cards y detalle MUST distinguir evidencia fuerte/media/baja,
  desconocidos y filtros cumplidos, y MUST presentar scores como indicadores
  con confianza, nunca como certeza. Los runs sin desglose (legacy del baseline
  de H2.3) MUST mostrarse sin razones fabricadas, con aviso de explicacion no
  disponible.
- **FR-019**: La web MUST manejar estados de carga, error recuperable, vacio y
  no autorizado en explicacion y comparacion, accesibles por teclado y lectores
  de pantalla.
- **FR-020** (P1): El comparador MUST permitir seleccionar listings del mismo
  radar hasta el limite, persistir la shortlist por busqueda y mostrarla en una
  matriz responsive con dimensiones auditables y navegacion al detalle.

#### Transversal

- **FR-021**: Los runs, las evaluaciones y las vistas de explicacion y
  comparacion MUST emitir eventos versionados de auditoria/telemetria sin PII
  innecesaria.
- **FR-022**: Este incremento MUST exponer los contratos HTTP de explicacion
  (UM-H3-019) y los contratos necesarios para la superficie web de H3.2, y MUST
  NO exponer consola operativa de scoring (H6).

### Key Entities

- **Scoring Policy Version**: definicion inmutable y versionada de criterios,
  pesos, normalizacion, gates, confianza, bonuses, penalizaciones y tie-breaks.
- **Evaluator**: evaluador generico con contrato comun de salida (score,
  confianza, evidencia); tipos iniciales numeric range, categorical, geo
  proximity, semantic feature.
- **Criterion Evaluation**: evaluacion persistida de un criterio contra un
  listing con criterio, inputs, contribucion y razon versionados.
- **Recommendation Run (v1)**: ejecucion atomica de scoring con snapshots
  congelados, policy version y score version; el fallido no reemplaza al
  valido.
- **Explanation**: desglose de razones, riesgos, datos faltantes y confianza
  con evidence refs, generado desde el run.
- **Evidence Ref**: referencia a la evidencia persistida (observacion,
  fragmento, fuente y version) que soporta una razon.
- **Structured Comparison**: comparacion hasta el limite con dimensiones
  homogeneas, faltantes visibles y tradeoffs sin ganador inventado.
- **Comparison Dimension**: dimension homogenea (misma unidad y fuente de
  valor) dentro de una comparacion; se compone de dimensiones fijas basicas
  (precio total, expensas, superficie, ambientes, dormitorios,
  ubicacion/precision, score con confianza) y de criterios activos del perfil
  con su evaluacion y evidencia.
- **Comparison Shortlist**: seleccion persistida de listings del mismo radar por
  busqueda (P1).

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Scoring policy | UM-H3-012 |
| User Story 2 - Evaluadores genericos | UM-H3-013 |
| User Story 3 - Desconocido vs negativo | UM-H3-014 |
| User Story 4 - Evaluaciones y scoring deterministico | UM-H3-015, UM-H3-016 |
| User Story 5 - Runs atomicos | UM-H3-017 |
| User Story 6 - Explicaciones desde evidencia | UM-H3-018 |
| User Story 7 - Contrato de explicacion | UM-H3-019 |
| User Story 8 - Comparacion estructurada | UM-H3-020 |
| User Story 9 - UI de razones e incertidumbre | UM-H3-021 |
| User Story 10 - Comparador persistente | UM-H3-022 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H3-012 | FR-001, FR-002, FR-003 | US1.1-US1.4, SC-002 |
| UM-H3-013 | FR-004, FR-005 | US2.1-US2.4, SC-003 |
| UM-H3-014 | FR-006 | US3.1-US3.3, SC-004 |
| UM-H3-015 | FR-007, FR-009 | US4.2, US4.4, SC-005 |
| UM-H3-016 | FR-008 | US4.1, US4.3, SC-001 |
| UM-H3-017 | FR-010, FR-011 | US5.1-US5.3, SC-006 |
| UM-H3-018 | FR-012, FR-013 | US6.1-US6.4, SC-007 |
| UM-H3-019 | FR-014, FR-015 | US7.1-US7.4, SC-008, SC-010 |
| UM-H3-020 | FR-016, FR-017 | US8.1-US8.5, SC-009 |
| UM-H3-021 | FR-018, FR-019 | US9.1-US9.4, SC-010, SC-011 |
| UM-H3-022 | FR-020 | US10.1-US10.4, SC-012 |
| Transversal (todos) | FR-021, FR-022 | SC-010, SC-011 |

## Constitution Alignment *(mandatory)*

- **Persistent product objects**: las evaluaciones de criterio, los runs, las
  explicaciones y las shortlists de comparacion son objetos persistentes y
  versionados vinculados a su busqueda; nada de lo que el usuario ve como razon
  vive solo en una respuesta efimera. Sustenta el principio I (radar como
  fuente de verdad).
- **Auditable deterministic matching**: el ranking final lo produce scoring
  v1 puro y deterministico sobre una policy versionada; el copy de explicacion
  es determinista por templates y 0 afirmaciones se sostienen sin evidencia
  interna. Sustenta el principio II y UM-H0-007.
- **Data lineage, observability and trust**: cada razon referencia evidence refs
  internas con fuente y version; cada run congela profile/feature snapshots,
  policy y score version; desconocido y evidencia negativa se distinguen y la
  incertidumbre se presenta honestamente. Sustenta el principio V y el
  guardrail de lineage completo.
- **Versioned prompts, models and schemas**: este incremento no incorpora
  redaccion generativa de explicaciones: el copy es determinista por templates
  (UM-H3-018). Si un incremento posterior la incorporara, deberia referenciar
  versiones inmutables y no agregar hechos.
- **Verification approach**: casos golden de policy y evaluadores, doble
  ejecucion para determinismo, fallo inducido para atomicidad, audit de evidence
  refs, casos de comparacion dentro/fuera de limite y de distintas busquedas, y
  revision de copy/accesibilidad de la web.
- **Dependency direction**: policy, evaluadores, scoring y explicaciones son
  dominio/aplicacion puros; los adapters (datos, y un modelo generativo solo si
  un incremento futuro lo incorpora) implementan puertos; la web consume
  contratos de Product API con permisos deny-by-default.
- **Minimal change**: el incremento se limita a UM-H3-012 a UM-H3-022 y excluye
  feedback (H3.3), dataset golden y regresiones (H3.4), chat (H4) y
  notificaciones (H5). El comparador persistente es P1.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Ejecutar scoring v1 dos veces sobre la misma entrada produce orden
  y desglose identicos en el 100% de los casos del conjunto de prueba; 0
  invocaciones dependen de red, almacenamiento o modelo externo.
- **SC-002**: El 100% de los cambios de policy queda versionado de forma
  inmutable; 0 mutaciones de versiones previas; el 100% de las policies
  publicadas valida pesos, normalizacion, gates y referencias.
- **SC-003**: El 100% de los casos golden de evaluadores genericos produce
  score, confianza y evidencia esperados bajo el contrato comun.
- **SC-004**: El 100% de los casos golden de desconocido vs evidencia negativa
  demuestra tratamiento distinguible; 0 desconocidos puntuan como mismatch.
- **SC-005**: El 100% de las evaluaciones de criterio persiste criterio, inputs,
  contribucion y razon con sus versiones; 0 evaluaciones sin version o de runs
  no publicados se usan en vistas de resultados.
- **SC-006**: El 100% de los runs del conjunto de prueba congela snapshots,
  candidate set y versiones antes de publicar; 0 runs fallidos reemplazan al
  ultimo valido y el 100% registra causa sin exponer parciales; 0 runs
  publicados se invalidan o re-ejecutan por cambios de observaciones o datos
  Silver en este incremento.
- **SC-007**: El 100% de las razones de las explicaciones cita evidence refs
  internas o declara desconocido; el 100% del copy es determinista por
  templates (doble ejecucion del mismo desglose produce el mismo texto); 0
  afirmaciones sin evidencia interna se publican.
- **SC-008**: El 100% de las consultas de explicacion respeta ownership con
  deny-by-default; 0 accesos cruzados devuelven datos.
- **SC-009**: El 100% de las comparaciones respeta el limite definido y usa
  dimensiones homogeneas con faltantes visibles; 0 comparaciones inventan un
  ganador; el 100% de las matrices incluye las dimensiones fijas basicas y los
  criterios activos del perfil con su evaluacion y evidencia.
- **SC-010**: El 100% de los runs, evaluaciones y vistas de explicacion y
  comparacion emite su evento versionado; 0 eventos contienen PII innecesaria.
- **SC-011**: El 100% de las superficies web revisadas distingue evidencia
  fuerte/media/baja y desconocidos y presenta scores con su confianza; 0
  superficies presentan scores como certeza ni mezclan versiones de policy; 0
  superficies fabrican razones para runs legacy del baseline de H2.3.
- **SC-012** (P1): El 100% de las shortlists de comparacion persiste por busqueda
  y sobrevive recarga; la matriz es usable en desktop/mobile con dimensiones
  auditables.

## Assumptions

- El alcance incluye exactamente UM-H3-012 a UM-H3-022 (Epica H3.2 - Scoring y
  explicaciones). El feedback (H3.3), el dataset golden y las regresiones de
  scoring (H3.4), el chat (H4) y las alertas (H5) quedan fuera y se especifican
  en sus propios incrementos.
- El scoring v1 evoluciona la maquinaria de runs de H2.3 (UM-H2-026 a
  UM-H2-028): se reutiliza la persistencia de recommendation runs/items, el
  congelamiento de snapshots y los triggers de run existentes (editar/reanudar
  perfil, importacion); se reemplaza el scoring baseline por la policy
  versionada con evaluadores. Los detalles de integracion con lo existente se
  deciden en el plan.
- Este incremento no incluye invalidacion ni re-ejecucion automatica de runs
  por cambios de observaciones o datos Silver (decision de clarificacion
  2026-08-07): los runs publicados quedan congelados y vigentes hasta un
  trigger existente; el recalculado automatico tras cambios relevantes es H3.3
  (UM-H3-030).
- Los conceptos, criterios ejecutables, observaciones y sus versiones de H3.1
  (UM-H3-001 a UM-H3-011) estan disponibles como entrada; este incremento
  consume evaluaciones de criterio sobre observaciones y registra nuevos tipos
  de evidencia solo si la policy los requiere.
- A diferencia de H3.1, este incremento SI expone contratos HTTP de Product API
  (UM-H3-019 lo exige y las stories WEB UM-H3-021 y UM-H3-022 requieren
  contratos para consumir datos); no se expone consola operativa de scoring,
  que pertenece a H6.
- La redaccion de explicaciones en v1 es 100% determinista: templates
  derivados del desglose, sin LLM ni proveedor externo en el camino critico
  (decision de clarificacion 2026-08-07). La redaccion generativa (UM-H3-018)
  queda fuera de este incremento; si se incorporara en un incremento posterior,
  deberia no agregar hechos y referenciar versiones inmutables.
- El score v1 mantiene la escala normalizada 0..1 heredada del scoring baseline
  de H2.3 (UM-H2-026), con la version de policy que lo produjo.
- El limite de comparacion es un parametro de politica: default 6 listings por
  comparacion, revisable en el plan sin cambiar el alcance.
- Las dimensiones del comparador son mixtas (decision de clarificacion
  2026-08-07): fijas basicas (precio total, expensas, superficie, ambientes,
  dormitorios, ubicacion/precision, score con confianza) mas los criterios
  activos del perfil con su evaluacion y evidencia; el conjunto exacto se afina
  en el plan sin cambiar el alcance.
- Los scores se presentan como indicadores normalizados con su nivel de
  confianza; el formato y el copy de incertidumbre exactos se definen en el
  plan y los contratos, alineados con UM-H0-007.
- La shortlist del comparador persiste por busqueda; las vistas de producto de
  shortlist/descartados con feedback y estados de decision son H3.3
  (UM-H3-025, UM-H3-026) y consumiran la misma persistencia.
- Los runs publicados con el scoring baseline de H2.3 (legacy) siguen visibles
  con score sin desglose y aviso de explicacion no disponible; 0 migracion ni
  backfill en este incremento (decision de clarificacion 2026-08-07); se
  reemplazan naturalmente cuando un trigger existente genera el primer run v1.
- Los eventos de runs, evaluaciones y vistas de explicacion/comparacion siguen
  el diccionario de eventos (UM-H0-013), sin PII innecesaria.
- El idioma de los casos golden y del copy de explicaciones es espanol (CABA),
  sobre el dataset controlado.
- El comparador persistente (UM-H3-022) es P1: se especifica con su prioridad y
  se ordena despues del primer recorrido interno del hito; no bloquea el camino
  critico de la beta.
- La verificacion de determinismo, atomicidad, lineage y eventos se ejecuta
  sobre el conjunto de prueba del harness con casos golden, de acuerdo con el
  DoD del proyecto; la superficie web se verifica con tests de componente y
  revision de accesibilidad/copy por convencion del proyecto.
