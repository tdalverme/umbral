# Feature Specification: Bronze Ingestion

**Feature Branch**: `002-bronze-ingestion`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "Especificar la epica H2.1 - Ingestion Bronze del backlog, con alcance exacto UM-H2-001 a UM-H2-008."

## Clarifications

### Session 2026-08-06

- Q: ¿Cómo debe tratarse la entrada operativa de importación (UM-H2-003) dado que
  el rol de operador (UM-H1-015) aún no está implementado? → A: Se especifica la
  capacidad completa con permiso de operador, deny-by-default y clave
  idempotente; la entrada operativa sólo se despliega o habilita cuando exista el
  rol, y hasta entonces queda restringida por controles del entorno. No se relaja
  seguridad.

## Operational Definitions

- **Lote de importacion**: conjunto acotado de registros de una unica fuente,
  entregado junto con la identidad de la fuente y la version del formato, que se
  procesa como una unidad. Cada lote tiene una clave/hash idempotente.
- **ImportSource**: interfaz que recibe un lote, la identidad de la fuente y la
  version del formato, y devuelve snapshots crudos y un reporte de ingesta, sin
  conocer ni depender de la normalizacion Silver.
- **Snapshot crudo inmutable**: representacion persistente de un registro tal
  como llego (payload), con hash de integridad, identidad de fuente, version,
  timestamps y referencia al contenido pesado. Una vez persistido no se modifica.
- **Contenido pesado**: payload extenso o media de un registro que se conserva en
  el almacenamiento de objetos con integridad verificable, referenciado desde el
  snapshot.
- **Import run**: registro de una ejecucion de importacion con estado, conteos,
  version de parser, actor, timestamps y errores resumidos.
- **Cuarentena por registro**: estado consultable de un registro rechazado que
  conserva codigo, regla incumplida, detalle y referencia al payload. No aborta
  el resto del lote.
- **Captura idempotente**: repetir un lote con la misma clave/hash produce el
  mismo resultado sin duplicar snapshots ni crear efectos nuevos.
- **Contrato de importacion**: especificacion publicada de campos
  requeridos/opcionales, formato, encoding, tamaño, version soportada y ejemplos
  validos/invalidos (UM-H0-009) contra la que se valida cada lote.
- **Entrada operativa**: superficie controlada mediante la cual una persona con
  permiso de operador sube un lote, indica fuente y version, y sigue el progreso
  de la importacion.

## Review and Measurement Protocol

- La puerta de salida del hito: una persona con permiso de operador importa un
  lote controlado; los registros validos llegan a snapshots Bronze inmutables y
  consultables, los invalidos a cuarentena con codigo y detalle, la repeticion
  con la misma clave no duplica efectos y el reporte de calidad refleja los
  conteos reales.
- El lote de referencia (fixture del harness) incluye registros validos,
  invalidos, duplicados, campos faltantes y valores anormales. Cada criterio de
  "100%" se calcula sobre todos los casos declarados en esa fixture.
- La idempotencia se verifica reimportando el lote de referencia con la misma
  clave/hash: el conjunto de snapshots y el run deben coincidir sin duplicados.
- La integridad de un snapshot se comprueba recalculando su hash y verificando
  que coincida con el registrado; el contenido pesado se recupera desde el
  almacenamiento y se verifica su integridad.
- Los permisos se miden con intentos de acceso no autorizado del conjunto de
  prueba, que deben rechazarse y registrarse.
- La entrada operativa debe poder recorrerse de punta a punta sobre el lote de
  referencia en un tiempo acotado (subir, ver progreso, obtener resultado).
- La normalizacion Silver, el dedupe y el matching NO se evaluan en este
  incremento; pertenecen a H2.2 y H2.3.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Importar un lote controlado de punta a punta (Priority: P1)

Como persona operadora con permiso, quiero subir un lote de datos de una fuente,
ver su progreso y obtener snapshots crudos confiables, para que las propiedades
lleguen a la base de producto sin errores silenciosos ni perdida de evidencia.

**Why this priority**: Sin captura confiable de lotes controlados no hay lista de
propiedades persistente sobre la cual construir busquedas, matching ni radar.

**Independent Test**: El lote de referencia (con registros validos e invalidos) se
sube por la entrada operativa y produce un run consultable, snapshots inmutables
para los validos y cuarentena consultable para los invalidos.

**Acceptance Scenarios**:

1. **Given** un lote controlado que cumple el contrato de importacion, **When** el
   operador lo sube indicando fuente y version, **Then** el run registra su estado
   y conteos, los registros validos quedan como snapshots crudos inmutables y los
   invalidos en cuarentena con detalle.
2. **Given** un archivo con formato, encoding, tamaño o version no soportados,
   **When** se intenta importar, **Then** el lote se rechaza con un diagnostico
   accionable que nombra la regla incumplida, sin procesar registros.
3. **Given** un registro con un campo invalido dentro de un lote por lo demas
   valido, **When** se procesa, **Then** ese registro queda en cuarentena con
   codigo, regla y referencia al payload, y el resto del lote continua.
4. **Given** una persona sin permiso de operador, **When** intenta iniciar o
   consultar una importacion, **Then** el acceso se rechaza y el intento queda
   registrado.
5. **Given** un lote procesado, **When** se consulta el run, **Then** el estado,
   los conteos y los errores resumidos son visibles durante y despues del
   procesamiento.

---

### User Story 2 - Repetir una importacion sin duplicar efectos (Priority: P2)

Como persona operadora, quiero reintentar la importacion de un mismo lote con la
misma clave idempotente sin duplicar snapshots ni efectos, para poder recuperar
fallos transitorios de forma segura.

**Why this priority**: La idempotencia evita que reintentos, reinicios o
reprocesamientos corrompan el inventario con duplicados.

**Independent Test**: Reimportar el lote de referencia con la misma clave/hash
produce el mismo resultado y un unico run, con cero snapshots duplicados.

**Acceptance Scenarios**:

1. **Given** un lote ya importado, **When** se reimporta con la misma clave/hash,
   **Then** no se crean snapshots duplicados ni efectos nuevos y se devuelve el
   resultado existente.
2. **Given** dos lotes con el mismo contenido pero distinta clave/hash, **When** se
   importan ambos, **Then** se tratan como importaciones independientes.
3. **Given** una importacion que falla a mitad de camino, **When** se reintenta con
   la misma identidad, **Then** los registros ya capturados no se duplican y el
   resultado final queda consistente.

---

### User Story 3 - Diagnosticar rechazos y evaluar la calidad del lote (Priority: P2)

Como persona responsable de datos, quiero consultar los registros rechazados y el
reporte de calidad de un lote, para decidir que corregir o descartar antes de que
los datos validos alimenten el producto.

**Why this priority**: Sin visibilidad de cuarentenas y calidad, los errores se
volverian silenciosos y contaminarian los datos que luego usa el producto.

**Independent Test**: El reporte de calidad del lote de referencia muestra conteos
exactos de aceptados, cuarentenados, duplicados y campos faltantes, y cada
registro en cuarentena es consultable con detalle y descargable de forma segura.

**Acceptance Scenarios**:

1. **Given** un lote procesado, **When** se consulta el reporte de calidad, **Then**
   muestra aceptados, cuarentenados, duplicados, campos faltantes y distribuciones
   anormales consistentes con los datos reales.
2. **Given** un registro en cuarentena, **When** se consulta su detalle, **Then** se
   ve codigo, regla incumplida, detalle accionable y referencia al payload.
3. **Given** un reporte generado, **When** se descarga, **Then** la descarga es
   segura y respeta los permisos del operador.
4. **Given** los snapshots del lote de referencia, **When** se verifica su
   integridad, **Then** el hash recalculado coincide y el contenido pesado se
   recupera desde el almacenamiento.

### Edge Cases

- Un archivo vacio, con solo encabezados o con encoding invalido debe rechazarse
  con diagnostico accionable.
- Un lote con tamaño mayor al permitido por el contrato debe rechazarse sin
  efectos parciales ni consumo indebido de almacenamiento.
- Un registro con valor ambiguo o fuera de rango debe ir a cuarentena y no
  detener la captura del resto.
- Una importacion interrumpida despues de persistir algunos snapshots debe poder
  reintentarse con la misma identidad sin duplicar los ya capturados.
- La misma clave idempotente no debe colisionar entre fuentes o versiones
  distintas.
- Un fallo del almacenamiento de objetos a mitad de lote no debe dejar snapshots
  huérfanos ni estados parciales confundibles con exito.
- Un registro en cuarentena no debe poder confundirse con un registro valido en
  conteos ni en consultas.
- Reintentos masivos o doble clic en la entrada operativa no deben generar
  importaciones paralelas del mismo lote.
- Una descarga del reporte o consulta sin permiso debe rechazarse y registrarse.

## Requirements *(mandatory)*

### Functional Requirements

#### Interfaz de fuente

- **FR-001**: El sistema MUST definir una interfaz de fuente de importacion que
  reciba un lote, la identidad de la fuente y la version del formato, y devuelva
  snapshots crudos y un reporte de ingesta sin depender de la normalizacion
  posterior (Silver).
- **FR-002**: La interfaz de fuente MUST contar con un adaptador que lea archivos
  del formato acordado y un reemplazo controlado de prueba con el mismo
  comportamiento observable.
- **FR-003**: El sistema MUST conservar la identidad de la fuente y la version del
  formato en cada elemento capturado.

#### Validacion contra el contrato

- **FR-004**: Cada archivo de lote MUST validarse contra el contrato de
  importacion publicado: formato, encoding, tamaño, estructura y version
  soportada.
- **FR-005**: Un lote que incumple el contrato a nivel de archivo MUST rechazarse
  con un diagnostico accionable que nombre la regla incumplida, sin procesar
  registros.
- **FR-006**: Un registro invalido MUST generar un error por registro accionable
  (campo, regla y valor referenciado) y MUST NO abortar la captura del resto del
  lote.
- **FR-007**: Los registros validos MUST continuar a la captura; los invalidos MUST
  quedar en cuarentena consultable.

#### Ejecuciones de importacion

- **FR-008**: Cada importacion MUST persistir un run con estado, conteos (total,
  aceptados, cuarentenados, duplicados), version de parser, actor, timestamps y
  errores resumidos.
- **FR-009**: El estado del run MUST ser consultable durante y despues del
  procesamiento, y los errores resumidos deben ser accionables.

#### Snapshots inmutables

- **FR-010**: Antes de cualquier transformacion, cada registro valido MUST
  persistirse como snapshot crudo inmutable con payload, hash de integridad,
  identidad de fuente, version y timestamps.
- **FR-011**: El contenido pesado MUST almacenarse en el almacenamiento de objetos
  con integridad verificable y referencia desde el snapshot.
- **FR-012**: Un snapshot persistido MUST ser inmutable; cualquier correccion MUST
  crear un nuevo snapshot conservando el anterior.

#### Idempotencia

- **FR-013**: Repetir un lote con la misma clave/hash MUST producir el mismo
  resultado sin duplicar snapshots ni crear ejecuciones o efectos nuevos.
- **FR-014**: Una clave/hash distinta MUST tratarse como una importacion
  independiente.

#### Cuarentena

- **FR-015**: Los registros rechazados MUST permanecer consultables con codigo,
  regla incumplida, detalle y referencia al payload.
- **FR-016**: La cuarentena MUST distinguirse claramente de los registros validos
  en conteos, consultas y reportes.

#### Reporte de calidad

- **FR-017**: El sistema MUST producir un reporte de calidad por lote con
  aceptados, cuarentenados, duplicados, campos faltantes y distribuciones
  anormales.
- **FR-018**: El reporte MUST poder descargarse de forma segura respetando los
  permisos del operador.
- **FR-019**: La emision de reportes y los eventos relevantes de importacion MUST
  quedar registrados para auditoria.

#### Entrada operativa

- **FR-020**: Una persona con permiso de operador MUST poder subir un lote
  controlado indicando fuente y version, con clave idempotente y seguimiento de
  progreso. La entrada operativa se despliega o habilita solo cuando el rol de
  operador (UM-H1-015) exista; hasta entonces permanece restringida por controles
  del entorno.
- **FR-021**: La entrada operativa MUST NO aceptar URLs arbitrarias; solo archivos
  subidos de forma controlada.
- **FR-022**: El sistema MUST aplicar deny-by-default a la iniciacion y consulta de
  importaciones, y MUST registrar los intentos no autorizados.

### Key Entities

- **Contrato de Importacion**: especificacion publicada (UM-H0-009) de campos,
  formatos, encoding, tamaños, versiones y ejemplos validos/invalidos contra la
  que se valida cada lote.
- **Fuente**: identidad de un proveedor de datos (identificador y version) que
  distingue la procedencia en cada snapshot y run.
- **Lote**: conjunto acotado de registros de una fuente con identidad idempotente
  (clave/hash) y version del formato.
- **Import Run**: ejecucion persistida de una importacion con estado, conteos,
  version de parser, actor, timestamps y errores resumidos.
- **Snapshot Crudo**: registro inmutable en Bronze con payload, hash, fuente,
  version, timestamps y referencia al contenido pesado.
- **Registro en Cuarentena**: registro rechazado consultable con codigo, regla,
  detalle y referencia al payload.
- **Reporte de Calidad**: resumen agregado de un lote con aceptados, cuarentena,
  duplicados, campos faltantes y distribuciones anormales.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Importar un lote controlado | UM-H2-001 a UM-H2-005, UM-H2-007 |
| User Story 2 - Repetir sin duplicar | UM-H2-006 |
| User Story 3 - Diagnosticar y evaluar calidad | UM-H2-007, UM-H2-008 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H2-001 | FR-001, FR-002, FR-003 | US1.1, SC-001 |
| UM-H2-002 | FR-004, FR-005, FR-006, FR-007 | US1.2-US1.3, SC-002 y SC-003 |
| UM-H2-003 | FR-020, FR-021, FR-022 | US1.1 y US1.4, SC-001 y SC-007-SC-008 |
| UM-H2-004 | FR-008, FR-009 | US1.1 y US1.5, SC-001 |
| UM-H2-005 | FR-010, FR-011, FR-012 | US1.1 y US3.4, SC-003 y SC-005 |
| UM-H2-006 | FR-013, FR-014 | US2.1-US2.3, SC-004 |
| UM-H2-007 | FR-006, FR-007, FR-015, FR-016 | US1.3 y US3.2, SC-003 y SC-006 |
| UM-H2-008 | FR-017, FR-018, FR-019 | US3.1 y US3.3, SC-006 |

## Constitution Alignment *(mandatory)*

- **Persistent product objects**: snapshots, runs y cuarentenas son objetos
  persistentes e inmutables; nada vive solo en logs o memoria. Esto habilita los
  listings persistentes futuros sin depender de chat ni estado efimero.
- **Evidence and audit needs**: cada snapshot conserva fuente, version, run, actor,
  timestamps e integridad, permitiendo reconstruir el recorrido de cada registro
  hasta Bronze y servir de base al lineage Bronze-Silver posterior.
- **LLM boundary**: no se incorpora un LLM en este incremento. Validacion,
  captura, cuarentena e idempotencia son codigo determinista y testeable.
- **Verification approach**: conformance con el contrato de importacion, casos
  golden de cuarentena, tests de idempotencia, verificacion de integridad de
  snapshots, pruebas de permisos y reporte de calidad contrastado contra los datos
  reales del lote de referencia.
- **Dependency direction**: ImportSource es un puerto del dominio/datos que no
  conoce Silver; el adaptador de archivo y el almacenamiento de objetos son
  infraestructura que implementan puertos. La entrada operativa cruza el caso de
  uso, no reglas internas.
- **Minimal change**: el incremento se limita a la captura Bronze y excluye
  normalizacion Silver, dedupe, matching y superficies de usuario final.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona con permiso de operador puede importar el lote de
  referencia de punta a punta y consultar el resultado en 5 minutos o menos.
- **SC-002**: El 100% de los archivos de prueba que violan formato, encoding,
  tamaño o version se rechazan con diagnostico accionable y cero registros
  procesados.
- **SC-003**: En el lote de referencia, el 100% de los registros validos llega a
  snapshot crudo y el 100% de los invalidos queda en cuarentena consultable con
  codigo, regla, detalle y payload referenciado.
- **SC-004**: Reimportar el lote de referencia con la misma clave/hash produce cero
  snapshots duplicados y un unico run con el mismo resultado.
- **SC-005**: El 100% de los snapshots del conjunto de prueba conserva integridad
  verificable y contenido pesado recuperable desde el almacenamiento.
- **SC-006**: El reporte de calidad del lote de referencia coincide al 100% con los
  conteos reales de aceptados, cuarentenados, duplicados y campos faltantes.
- **SC-007**: El 100% de los intentos de iniciar o consultar importaciones sin
  permiso de operador es rechazado y queda registrado.
- **SC-008**: La entrada operativa rechaza el 100% de los intentos de importar
  mediante URLs arbitrarias.
- **SC-009**: El 100% de los snapshots del conjunto de prueba permite reconstruir
  lote, fuente, version y run que lo produjo.

## Assumptions

- El alcance incluye exactamente UM-H2-001 a UM-H2-008 (Epica H2.1 - Ingestion
  Bronze). La normalizacion Silver (UM-H2-009 a UM-H2-018), el dedupe y el
  matching pertenecen a incrementos posteriores.
- El contrato de importacion v1 (UM-H0-009) es un prerrequisito consumido por este
  incremento. Si no esta publicado al momento de planificar, la redaccion minima
  del contrato forma parte del alcance de este incremento para poder validar.
- La entrada operativa (UM-H2-003) depende del rol de operador (UM-H1-015). Hasta
  que la identidad/roles existan, la entrada operativa debe permanecer restringida
  por controles del entorno, sin dejar de definirse la capacidad esperada.
- Los lotes de beta provienen de una fuente controlada acordada (CSV o JSON),
  segun UM-H0-008; el scraping queda fuera del camino critico.
- Los registros invalidos no bloquean el lote; se aislan en cuarentena.
- No se convierte moneda ni se normalizan atributos en este incremento; eso
  pertenece a H2.2.
- El almacenamiento de objetos y las primitives de identidad/auditoria del runtime
  ya estan disponibles desde el incremento `foundation-runtime`.
