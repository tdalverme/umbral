# Feature Specification: Señales urbanas declarativas

**Feature Branch**: `017-urban-signals`

**Created**: 2026-08-17

**Status**: Draft

**Input**: Rediseñar el módulo de contexto urbano para que las preferencias de cercanía (cafes, parques, transporte, ruido, caminabilidad, vida nocturna, comercial/residencial, etc.) se computen desde datos abiertos de OpenStreetMap mediante un contrato declarativo y versionado, se conserven como señales factuales por listing y el scoring decida cómo ponderarlas.

## Operational Definitions

- **Señal urbana**: valor factual (0-1) que describe el entorno de un listing — p. ej. caminabilidad, acceso a transporte, riesgo de ruido. Es independiente de las preferencias de cualquier persona.
- **Primitiva urbana**: métrica cruda por categoría de POI o feature lineal — p. ej. `count_300m`, `nearest_m` — calculada desde las distancias del listing a los puntos de interés.
- **Categoría urbana**: agrupación de tags de OpenStreetMap en un concepto reutilizable — p. ej. `cafe`, `subway_station`, `green_space`, `nightlife`.
- **Señal base**: señal declarada como fórmula sobre primitivas.
- **Señal compuesta**: señal declarada como combinación de otras señales (p. ej. `noise_risk` combina `nightlife_intensity` y ruido de infraestructura).
- **Contrato urbano**: documento declarativo y versionado que define el mapping de tags, las primitivas, las señales y las reglas de normalización y confianza.
- **Snapshot urbano**: instancia inmutable de datos de OpenStreetMap (archivo, hash, fecha de datos, atribución) de la que derivan las señales.
- **Normalización por barrio**: comparación del valor crudo de una señal contra la distribución (percentil) de los listings del mismo barrio.
- **Observación urbana**: la señal ya vinculada a un concepto evaluable, persistida con score, confidence, evidencia y versiones — el formato que consume el scoring.
- **Desconocimiento**: estado explícito de una señal cuando no hay datos suficientes; el scoring MUST NOT tratarlo como un valor real.

## Relationship to Existing Features

Esta feature reemplaza el mecanismo de contexto urbano actual (señales de tipo fijo `cafe`/`transport`/`green_space` con conteo simple por radio) y migra los concepts urbanos existentes (`proximidad_cafes`, `acceso_transporte`) del mecanismo `proxy` a referencias por nombre de señal (`signal_ref`). Conserva: el scoring determinista, las observaciones versionadas, la evidencia y las explicaciones. No reemplaza la ingestión de listings ni las fuentes de datos de vivienda.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Preferencias de entorno expresadas naturalmente (Priority: P1)

Como persona que busca vivienda, quiero expresar "quiero estar cerca de cafes", "prefiero un lugar tranquilo" o "necesito buen transporte", para que Umbral evalúe esas preferencias con datos reales del entorno y me explique por qué.

**Why this priority**: Es el valor diferencial del contexto urbano — sin datos, esas preferencias quedan sin evidencia y no influyen el ranking.

**Independent Test**: Una persona expresa una preferencia de entorno y el radar la conserva; cuando el listing tiene datos urbanos, la preferencia recibe una observación con evidencia y contribuye al ordenamiento con confianza visible; cuando no los tiene, se conserva con desconocimiento explícito.

**Acceptance Scenarios**:

1. **Given** un radar con la preferencia "cerca de cafes" y listings con datos urbanos, **When** se actualizan los resultados, **Then** la preferencia recibe una observación con score, confidence y evidencia (conteos y distancias), y contribuye al ordenamiento.
2. **Given** un listing sin coordenadas precisas, **When** se evalúan sus señales urbanas, **Then** no se le computan señales y las preferencias urbanas se reportan como dato faltante, no como valor medio.
3. **Given** una señal con datos parciales (una categoría sin POIs en el radio), **When** se computa la señal, **Then** su confidence refleja la cobertura de inputs y el desconocimiento es explícito.
4. **Given** un listing en un barrio con poca muestra, **When** se normaliza su señal, **Then** se compara contra toda la ciudad con confidence rebajada y la limitación es visible en la explicación.

### User Story 2 - Comparación justa entre barrios (Priority: P1)

Como persona que compara departamentos en distintos barrios, quiero que las señales de entorno no favorezcan sistemáticamente a los barrios mejor mapeados en OpenStreetMap, para que el ranking sea justo.

**Why this priority**: La cobertura de OSM es desigual por barrio; sin normalización, Palermo ganaría siempre en densidad de cafes por mapeo, no por realidad.

**Independent Test**: Dos listings con la misma densidad cruda de cafes en barrios con cobertura de mapeo distinta obtienen señales normalizadas comparables dentro de su contexto, y la explicación declara el alcance de comparación.

**Acceptance Scenarios**:

1. **Given** señales de densidad (cafes, caminabilidad, vida nocturna, comercios), **When** se normalizan, **Then** se comparan contra la distribución del propio barrio.
2. **Given** señales de distancia a infraestructura mayor (subte, parque grande, hospital), **When** se normalizan, **Then** permanecen absolutas — no se distorsiona el significado de "un parque a 200m".
3. **Given** un barrio con menos listings que el mínimo de muestra declarado, **When** se normaliza, **Then** la señal cae a comparación contra toda la ciudad con confidence rebajada y limitación visible.
4. **Given** cualquier señal normalizada, **When** se explica, **Then** la explicación cita el alcance ("comparado con tu barrio" o "comparado con toda la ciudad") y los datos crudos que la sustentan.

### User Story 3 - Agregar una señal nueva sin tocar el ranking (Priority: P2)

Como equipo de producto, quiero agregar una señal nueva (p. ej. "escuela cerca") declarándola en el contrato, para no tocar código de scoring ni de ingesta.

**Why this priority**: La expansibilidad es el requisito central del rediseño; si agregar una señal requiere código, el contrato no cumple su propósito.

**Independent Test**: Una señal nueva declarada en el contrato se computa, se persiste y se expone sin cambios de código en el scoring ni en los workers de criterios.

**Acceptance Scenarios**:

1. **Given** el contrato versionado, **When** se agrega una categoría nueva (tags OSM) y una señal que la usa, **Then** la nueva señal se computa en el batch siguiente con su propia versión de contrato.
2. **Given** un cambio de contrato (señal o categoría nueva), **When** se ejecuta el batch, **Then** todas las observaciones urbanas se recalculan con la nueva versión y las anteriores quedan fuera de vigencia.
3. **Given** una señal que no alimenta ningún concepto del scoring, **When** se computa, **Then** se conserva como dato disponible sin generar observaciones espurias.
4. **Given** la confianza de una señal, **When** se declara en el contrato, **Then** se deriva de la cobertura de sus inputs con una regla única versionada.

### User Story 4 - Datos urbanos auditables y licenciados (Priority: P2)

Como operador del producto, quiero saber de qué fuente y fecha provienen las señales urbanas y cumplir la licencia de los datos, para auditar y operar con confianza.

**Why this priority**: Los datos de OpenStreetMap tienen obligaciones de atribución y frescura que afectan el producto.

**Independent Test**: Cada observación urbana permite trazar su snapshot (fuente, fecha de datos, hash) y la aplicación muestra la atribución de OpenStreetMap en una superficie global visible.

**Acceptance Scenarios**:

1. **Given** un snapshot urbano importado, **When** se inspecciona, **Then** declara fuente, fecha de datos, hash y atribución.
2. **Given** cualquier observación urbana, **When** se audita, **Then** se puede trazar a la versión de contrato y al snapshot del que derivó.
3. **Given** la aplicación con señales urbanas visibles, **When** el usuario navega el producto, **Then** la atribución de OpenStreetMap es visible en una superficie global (footer o página de licencias).
4. **Given** un snapshot desactualizado (cambio de contrato o reimport), **When** se recalculan señales, **Then** los listings con coordenadas precisas se recomputan por completo y ninguno conserva señales de un snapshot fuera de vigencia.

### Edge Cases

- Un listing sin coordenadas o con precisión de barrio: se excluye de señales urbanas.
- Un barrio con menos listings que el mínimo de muestra: fallback a comparación global con confidence rebajada.
- Una señal con alguna primitiva sin datos: confidence proporcional a la cobertura; la señal no se anula.
- Un snapshot reimportado con cambios: recalcular todos los listings con coordenadas precisas.
- Un listing nuevo entre batches: se normaliza contra la tabla de estadísticas del barrio ya precomputada.
- Una categoría OSM nueva que no alimenta señales existentes: se registra y se conserva sin observaciones espurias.
- Un cambio de contrato a mitad del batch: se aborta la vigencia del snapshot anterior; los resultados viejos no se muestran como actuales.
- Un concepto con `signal_ref` que no tiene datos urbanos: la observación queda como desconocimiento, no como cero.
- Una señal compuesta con una señal base ausente: la confidence de la compuesta refleja la ausencia.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Umbral MUST conservar cada señal urbana como un valor factual por listing, independiente de las preferencias de cualquier persona.
- **FR-002**: El contrato urbano MUST declarar el mapping de tags de OpenStreetMap a categorías, las primitivas, las señales base, las señales compuestas y las reglas de normalización y confianza.
- **FR-003**: El contrato urbano MUST versionarse como un todo; cualquier cambio de contrato MUST invalidar las observaciones urbanas previas y requerir recálculo.
- **FR-004**: Una señal declarada en el contrato MUST poder computarse y persistirse sin cambios de código en el scoring ni en los workers de criterios.
- **FR-005**: Las señales de densidad MUST normalizarse por barrio; las señales de distancia a infraestructura mayor MUST permanecer absolutas. El modo de cada señal MUST declararse en el contrato.
- **FR-006**: La normalización por barrio MUST usar percentiles precomputados en una tabla de estadísticas por barrio, recalculada en el mismo job de snapshot.
- **FR-007**: El contrato MUST declarar un mínimo de muestra por barrio; por debajo, la señal MUST compararse contra toda la ciudad con confidence rebajada y limitación visible.
- **FR-008**: Cada observación urbana MUST conservar el valor crudo (evidencia) y el valor normalizado (para scoring) por separado.
- **FR-009**: La explicación de una señal urbana MUST citar los datos crudos (conteos, distancias) y el alcance de comparación, sin depender de texto generativo.
- **FR-010**: El desconocimiento (datos ausentes) MUST modelarse explícitamente por señal y MUST NOT tratarse como un valor real por el scoring.
- **FR-011**: Los listings sin coordenadas precisas MUST excluirse de señales urbanas.
- **FR-012**: La confidence de una señal MUST derivarse de la cobertura de sus inputs según una regla única declarada en el contrato.
- **FR-013**: Las señales urbanas MUST entregarse al scoring como observaciones versionadas (score, confidence, evidencia, versiones), sin cambiar el motor de scoring.
- **FR-014**: Los concepts urbanos MUST referenciar señales por nombre (`signal_ref`), reemplazando el mecanismo `proxy` existente.
- **FR-015**: El scoring MUST consumir las observaciones urbanas con un evaluador específico de score normalizado.
- **FR-016**: Cada snapshot urbano MUST declarar fuente, fecha de datos, hash y atribución.
- **FR-017**: La atribución de OpenStreetMap MUST ser visible en una superficie global de la aplicación.
- **FR-018**: El import de un snapshot urbano MUST ejecutarse mediante un comando operativo que descarga, verifica, almacena e importa; MUST NOT depender de la red en el worker de importación.
- **FR-019**: Al reimportar un snapshot o cambiar el contrato, MUST recalcularse las señales de todos los listings con coordenadas precisas.
- **FR-020**: Un listing nuevo entre batches MUST normalizarse contra la tabla de estadísticas del barrio vigente, sin esperar el próximo batch.
- **FR-021**: Las observaciones de señales sin datos urbanos MUST quedar como desconocimiento y MUST NOT reportarse como valor cero.
- **FR-022**: La falla de un batch a mitad de camino MUST dejar los listings afectados como sin datos vigentes, nunca como datos de un snapshot viejo.

### Key Entities

- **Contrato urbano**: documento versionado con mapping de tags, primitivas, señales, normalización, confianza, fuente y atribución.
- **Snapshot urbano**: archivo de datos de OpenStreetMap con fuente, hash, fecha y estado.
- **Categoría urbana**: agrupación de tags de OpenStreetMap.
- **Primitiva urbana**: métrica cruda por categoría (conteos y distancias).
- **Señal urbana**: valor 0-1 factual por listing, base o compuesta.
- **Observación urbana**: señal vinculada a un concepto, con score, confidence, evidencia, versión de contrato y snapshot.
- **Estadística de barrio**: percentiles y muestra por barrio y señal, precomputados en el batch.
- **Preferencia de entorno**: deseo expresado que referencia una señal por nombre.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las señales declaradas en el contrato se computan y persisten en el batch de validación con sus valores crudo y normalizado.
- **SC-002**: El 100% de las señales de densidad se normalizan por barrio y el 100% de las señales de distancia a infraestructura mayor permanecen absolutas, según lo declarado en el contrato.
- **SC-003**: El 100% de los barrios con muestra insuficiente usan fallback global con confidence rebajada y limitación visible.
- **SC-004**: El 100% de los listings sin coordenadas precisas quedan excluidos de señales urbanas y sus preferencias se reportan como dato faltante.
- **SC-005**: Una señal nueva agregada al contrato se computa y expone sin cambios en el scoring ni en los workers de criterios, verificable con un caso de prueba de contrato.
- **SC-006**: El 100% de las observaciones urbanas permiten trazar su contrato y snapshot (fuente, fecha, hash).
- **SC-007**: Un reimport de snapshot recalcula el 100% de los listings con coordenadas precisas y ningún listing conserva señales de un snapshot fuera de vigencia.
- **SC-008**: La atribución de OpenStreetMap es visible en una superficie global de la aplicación.
- **SC-009**: El tiempo de recálculo de señales para la totalidad de los listings con coordenadas de la beta no bloquea la operación del chat ni del scoring (se ejecuta en batch).
- **SC-010**: El 100% de los casos de validación del contrato (estructura, referencias, pesos, normalización) pasan en el harness.

## Assumptions

- La beta se enfoca en alquileres residenciales en CABA; el snapshot urbano cubre CABA.
- Los datos provienen de OpenStreetMap vía un extracto de Geofabrik de Argentina (archivo único, actualizable manualmente).
- La descarga del snapshot la realiza un operador a un almacenamiento de objetos; el worker importa desde allí.
- La precisión geográfica de los listings distingue coordenadas exactas/de cuadra (elegibles) de solo barrio (excluidas).
- La frecuencia de reimport del snapshot es manual y poco frecuente (mensual como referencia).
- Una señal nueva no requiere nuevos matchers; las preferencias de entorno se modelan como concepts con `signal_ref`.
- La normalización por barrio usa percentiles; el percentil específico y el mínimo de muestra se declaran en el contrato.
- El contrato urbano se registra como una versión de extracción más, reutilizando el lineage existente de observaciones.

## Out of Scope

- Garantizar la cobertura completa de OpenStreetMap en todos los barrios (se mitiga con normalización, no con datos inventados).
- Fuentes comerciales de datos urbanos.
- Actualización automática del snapshot (se mantiene manual).
- Rediseñar la ingestión de listings, el pipeline Bronze/Silver o las notificaciones.
- Señales en tiempo real (transporte en vivo, horarios de locales).
- Comparación entre ciudades (la normalización es por barrio dentro de la ciudad activa).
