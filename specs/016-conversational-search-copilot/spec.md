# Feature Specification: Copiloto conversacional de busqueda

**Feature Branch**: `016-conversational-search-copilot`

**Created**: 2026-08-14

**Status**: Draft

**Input**: User description: "Redisenar el chat como corazon de Umbral: debe crear y refinar busquedas persistentes desde lenguaje natural incompleto, comprender preferencias subjetivas sin convertir cada frase en un concepto nuevo, conservar el contexto entre turnos, aplicar cambios reversibles sin burocracia y demostrar su calidad con trayectorias conversacionales reales."

## Operational Definitions

- **Radar**: busqueda persistente de vivienda de una persona. Puede nacer parcial y ganar precision durante la conversacion; su estado durable, no el historial del chat, es la fuente de verdad operativa.
- **Deseo expresado**: formulacion completa y contextual de lo que la persona busca o evita. Es la fuente de verdad de sus preferencias aunque Umbral aun no pueda evaluarla.
- **Vinculacion de criterio**: interpretacion versionada que relaciona un deseo expresado con cero, una o varias capacidades evaluables, declarando confianza, evidencia y limitaciones.
- **Hecho de preferencia**: interpretacion estructurada y vigente de la parte computable de un deseo; no reemplaza ni recorta el deseo original.
- **Criterio compilado**: condicion ejecutable que puede participar del filtrado o del ordenamiento final. Solo se genera cuando existe una capacidad evaluable y auditable.
- **Preferencia suave**: deseo que modifica el orden relativo de oportunidades sin excluirlas.
- **Filtro duro**: condicion binaria que excluye oportunidades. Un deseo descriptivo no se convierte en filtro duro sin lenguaje explicito de exclusion, capacidad confiable e impacto visible cuando sea material.
- **Contexto conversacional activo**: radar, anuncio, accion pendiente, respuestas ya dadas y referencias verificables que determinan como interpretar el siguiente mensaje.
- **Trayectoria conversacional**: secuencia verificable de estados y turnos que parte de un contexto inicial y termina en un estado durable esperado, incluyendo comportamientos prohibidos.

## Relationship to Existing Features

Esta feature reemplaza, cuando exista conflicto, las reglas conversacionales de `011-conversational-ui`, `014-soft-preferences-chat` y `015-catalog-concept-expansion`. Conserva sus objetos persistentes, auditoria, observaciones, scoring deterministico y evidencia; reemplaza el formulario conversacional, la confirmacion universal y el rechazo de preferencias fuera de un vocabulario cerrado.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Crear y refinar un radar desde una intencion parcial (Priority: P1)

Como persona que busca vivienda, quiero empezar hablando con naturalidad aunque todavia no sepa zona, presupuesto o todos mis criterios, para recibir valor sin completar primero un formulario.

**Why this priority**: Si el primer mensaje no produce una busqueda durable y util, el chat sigue siendo una capa costosa sobre el formulario existente.

**Independent Test**: Una persona sin radar escribe una intencion parcial y termina el primer turno con un radar persistente que conserva todo lo expresado y puede seguir refinandose.

**Acceptance Scenarios**:

1. **Given** una persona sin radar, **When** escribe "quiero un depto luminoso y cerca del subte", **Then** Umbral crea un radar parcial, conserva ambos deseos y no exige zona ni presupuesto para persistirlo.
2. **Given** un radar sin zona, **When** la persona dice "cualquiera, pero cerca de un parque", **Then** el alcance geografico abierto queda registrado como una decision valida y Umbral no vuelve a preguntar por zona sin una razon nueva y explicita.
3. **Given** un mensaje con zona y varias preferencias reversibles, **When** Umbral puede interpretarlas sin contradiccion material, **Then** actualiza el radar en el mismo turno y comunica brevemente el nuevo estado sin solicitar confirmacion por cada cambio.
4. **Given** una intencion que omite un dato de alto impacto, **When** existe una interpretacion util y reversible, **Then** Umbral avanza con esa interpretacion y pregunta como maximo una aclaracion que cambie materialmente los resultados.

---

### User Story 2 - Expresar preferencias personales sin ampliar el esquema por usuario (Priority: P1)

Como persona con gustos propios, quiero expresar deseos como "cocina grande", "cafes donde pueda trabajar" o "un lugar tranquilo", para que Umbral los recuerde y use hasta el limite de la evidencia disponible sin rechazarlos ni fingir precision.

**Why this priority**: La diversidad personal es el valor diferencial del chat; limitarla a aliases predefinidos reproduce el formulario y destruye confianza.

**Independent Test**: Un deseo fuera del catalogo se conserva completo, recibe una vinculacion estructurada, semantica o no evaluable, y su influencia en los resultados coincide con la evidencia declarada.

**Acceptance Scenarios**:

1. **Given** un deseo que no coincide con un concepto compartido, **When** la persona lo expresa, **Then** Umbral lo conserva como deseo expresado y no responde con una lista cerrada de preferencias permitidas.
2. **Given** un deseo con evidencia estructurada confiable, **When** se actualizan resultados, **Then** su parte computable contribuye normalmente y puede explicarse con evidencia.
3. **Given** un deseo sustentado solo por evidencia semantica, **When** se actualizan resultados, **Then** contribuye unicamente como preferencia suave con confianza visible.
4. **Given** un deseo sin evidencia verificable, **When** se actualizan resultados, **Then** se conserva pero aporta cero al ordenamiento y Umbral declara honestamente la limitacion.
5. **Given** un mensaje que combina partes soportadas, tentativas y no evaluables, **When** se procesa, **Then** cada parte conserva su propio resultado sin rechazar el mensaje completo ni omitir silenciosamente informacion.

---

### User Story 3 - Mantener continuidad, corregir y cambiar de opinion (Priority: P1)

Como persona que conversa de forma incremental, quiero que Umbral recuerde que respuesta espera, incorpore correcciones y entienda varios actos en una frase, para no caer en loops ni mutaciones sobre objetos equivocados.

**Why this priority**: Perder el estado entre turnos rompe la confianza mas rapido que una interpretacion imperfecta y puede escribir feedback incorrecto.

**Independent Test**: Una trayectoria con propuesta pendiente, confirmacion, preferencia adicional y correccion termina en el estado durable correcto sin preguntas repetidas ni feedback espurio.

**Acceptance Scenarios**:

1. **Given** una accion pendiente, **When** la persona responde "confirmo", **Then** Umbral resuelve esa accion y nunca interpreta el mensaje como feedback de un anuncio.
2. **Given** una accion pendiente, **When** la persona dice "si, confirmo, y tambien quiero balcon", **Then** Umbral resuelve la accion y registra el deseo adicional en el mismo turno.
3. **Given** una respuesta ya registrada, **When** un paso posterior no aporta evidencia de que haya cambiado, **Then** Umbral no repite la misma pregunta.
4. **Given** una preferencia suave vigente, **When** la persona dice "en realidad el balcon no me importa", **Then** el cambio reversible se aplica, el estado anterior queda trazable y la respuesta siguiente refleja la correccion.
5. **Given** una contradiccion ambigua o un cambio material de filtro duro, **When** no existe una interpretacion segura, **Then** Umbral muestra el impacto y solicita una unica decision antes de aplicarlo.

---

### User Story 4 - Entender que influye en los resultados y recuperarse de cero matches (Priority: P2)

Como persona que evalua oportunidades, quiero saber de forma natural que entendio Umbral, que pudo comprobar y por que no hay resultados, para corregir la busqueda sin perder control.

**Why this priority**: La personalizacion sin transparencia se siente arbitraria; la recuperacion guiada evita que un radar vacio sea un callejon sin salida.

**Independent Test**: Un radar con preferencias de distinta confianza y un filtro que vacia resultados muestra el estado comprensible, identifica el bloqueo y propone alternativas sin alterar silenciosamente la intencion.

**Acceptance Scenarios**:

1. **Given** deseos con evidencia desigual, **When** Umbral confirma el cambio, **Then** resume en lenguaje natural que aplico y que limitaciones conserva, con detalle auditable disponible fuera del mensaje.
2. **Given** cero resultados por filtros duros, **When** finaliza la evaluacion, **Then** Umbral identifica los filtros responsables y ofrece relajaciones concretas sin aplicarlas.
3. **Given** preferencias suaves imposibles de satisfacer, **When** hay candidatos que cumplen los filtros duros, **Then** Umbral mantiene candidatos y explica los tradeoffs en lugar de devolver cero resultados.
4. **Given** varios cambios consecutivos, **When** existen evaluaciones anteriores todavia en curso, **Then** el estado mas reciente permanece visible y ningun resultado obsoleto reemplaza al vigente.

---

### User Story 5 - Aprender sin inventar gustos (Priority: P2)

Como persona que usa Umbral repetidamente, quiero que mis declaraciones y feedback mejoren la busqueda sin que clics accidentales se conviertan en preferencias, para sentir personalizacion sin perder agencia.

**Why this priority**: El aprendizaje aporta valor acumulativo, pero inferencias silenciosas o globales pueden contradecir necesidades situacionales.

**Independent Test**: Declaraciones, feedback deliberado y comportamiento pasivo producen niveles de autoridad distintos y nunca crean filtros duros ni pisan una instruccion explicita.

**Acceptance Scenarios**:

1. **Given** una declaracion explicita y una señal pasiva contradictoria, **When** se calibra la busqueda, **Then** la declaracion explicita prevalece.
2. **Given** likes, dislikes o correcciones deliberadas, **When** se acumula evidencia, **Then** pueden ajustar la confianza o importancia de preferencias suaves de ese radar con trazabilidad.
3. **Given** vistas, clics o permanencia, **When** sugieren un patron, **Then** generan como maximo una hipotesis o sugerencia y nunca una preferencia dura aplicada silenciosamente.
4. **Given** preferencias aprendidas en otro radar, **When** se crea uno nuevo, **Then** pueden sugerirse como punto de partida pero no se aplican sin que la persona las adopte.

---

### User Story 6 - Trabajar con varios radares y referencias verificables (Priority: P2)

Como persona con distintas busquedas, quiero saber que radar y anuncio estoy modificando, para usar referencias naturales como "este depto" sin escribir sobre el contexto equivocado.

**Why this priority**: Las preferencias dependen de la busqueda y una referencia equivocada puede producir decisiones o aprendizaje falsos.

**Independent Test**: Con dos radares y varios anuncios visibles, Umbral usa el contexto activo cuando es inequivoco y pide aclaracion solo cuando existen varios candidatos posibles.

**Acceptance Scenarios**:

1. **Given** varios radares, **When** uno esta activo y visible, **Then** los refinamientos inequivocos se aplican a ese radar sin preguntar de nuevo.
2. **Given** varios radares sin un contexto activo inequivoco, **When** llega un refinamiento, **Then** Umbral pregunta cual modificar antes de escribir.
3. **Given** una referencia como "este depto", **When** existe una unica tarjeta seleccionada o un unico anuncio referido, **Then** Umbral usa esa referencia verificable.
4. **Given** una accion pendiente y un anuncio visible, **When** la persona confirma, **Then** la accion pendiente tiene prioridad sobre el anuncio.

### Edge Cases

- La persona contradice dos preferencias dentro del mismo mensaje.
- Una aclaracion pendiente vence antes de que llegue la respuesta.
- La persona cambia de radar mientras hay una evaluacion en curso.
- Una expresion podria mapearse a varias capacidades con impactos distintos.
- La evidencia semantica contradice un dato estructurado mas confiable.
- Una preferencia solicita una caracteristica prohibida por las reglas de equidad o privacidad.
- La persona intenta convertir en filtro duro una caracteristica que Umbral no puede evaluar de forma confiable.
- El radar queda sin ningun criterio evaluable pero conserva deseos expresados.
- La persona elimina o cambia un deseo mientras todavia existe una interpretacion anterior activa.
- Un mensaje referencia simultaneamente una accion pendiente y mas de un anuncio.
- Falla una actualizacion de resultados despues de que el cambio de intencion ya quedo persistido.
- Dos mensajes llegan muy cerca entre si y el segundo vuelve obsoleto al primero.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Umbral MUST crear un radar durable desde la primera intencion de busqueda significativa cuando la persona aun no tenga uno.
- **FR-002**: Un radar MUST poder existir y refinarse sin zona, presupuesto u otros campos tradicionalmente obligatorios cuando la persona no los haya definido.
- **FR-003**: El estado durable del radar MUST ser la fuente de verdad operativa; ningun deseo, criterio aplicado o decision relevante puede vivir solo en el historial del chat.
- **FR-004**: Umbral MUST reconocer y procesar varios actos compatibles dentro del mismo mensaje.
- **FR-005**: La accion o aclaracion pendiente MUST tener precedencia sobre la clasificacion general del siguiente mensaje.
- **FR-006**: Umbral MUST conservar un contexto activo verificable que incluya radar, anuncio, accion pendiente y respuestas relevantes ya dadas.
- **FR-007**: Umbral MUST preservar cada deseo expresado con su formulacion original, alcance de radar, fuente, fecha, estado e historial de reemplazo.
- **FR-008**: Umbral MUST separar el deseo expresado, su vinculacion con capacidades, el hecho de preferencia computable y el criterio compilado.
- **FR-009**: Cada vinculacion MUST declarar si es estructurada, semantica o no evaluable, junto con confianza, evidencia, version de interpretacion y limitaciones.
- **FR-010**: Una expresion fuera del catalogo MUST conservarse y recibir un estado accionable; no puede rechazarse solo por no coincidir con un vocabulario cerrado.
- **FR-011**: Los deseos descriptivos MUST comenzar como preferencias suaves salvo que la persona exprese exclusion y exista una capacidad confiable para aplicarla.
- **FR-012**: Los cambios suaves, aditivos y reversibles MUST aplicarse sin confirmacion previa y comunicarse de forma corregible.
- **FR-013**: Umbral MUST solicitar confirmacion antes de aplicar eliminaciones irreversibles, contradicciones ambiguas, conversiones a filtro duro o cambios con impacto material no evidente.
- **FR-014**: Cambiar una preferencia MUST preservar la historia anterior y dejar una unica interpretacion vigente por alcance compatible.
- **FR-015**: Las declaraciones explicitas MUST prevalecer sobre feedback deliberado, y el feedback deliberado MUST prevalecer sobre señales pasivas.
- **FR-016**: Las señales pasivas MUST NOT crear filtros duros, contradecir silenciosamente declaraciones explicitas ni aplicarse globalmente a otros radares.
- **FR-017**: Una preferencia sin evidencia verificable MUST aportar cero al ordenamiento final aunque su deseo original permanezca vigente.
- **FR-018**: La evidencia semantica MAY contribuir unicamente como preferencia suave, con confianza y procedencia visibles.
- **FR-019**: Los mensajes con interpretacion parcial MUST preservar todas sus partes y reportar por separado cuales fueron aplicadas, cuales son tentativas y cuales no son evaluables.
- **FR-020**: Umbral MUST evitar preguntas repetidas cuando la respuesta ya exista y no haya evidencia explicita de cambio o invalidez.
- **FR-021**: Ante cero resultados, Umbral MUST identificar los filtros duros responsables y proponer relajaciones sin aplicarlas automaticamente.
- **FR-022**: Las preferencias suaves MUST NOT eliminar candidatos que cumplen los filtros duros.
- **FR-023**: Cuando existan varios radares o referencias posibles, Umbral MUST usar contexto visible inequivoco o solicitar aclaracion antes de mutar estado.
- **FR-024**: Una referencia a una accion pendiente MUST tener prioridad sobre referencias incidentales a anuncios visibles.
- **FR-025**: El estado actualizado del radar MUST quedar disponible inmediatamente aunque la actualizacion de resultados continue en segundo plano.
- **FR-026**: Resultados producidos para una version obsoleta del radar MUST NOT reemplazar los resultados de una version posterior.
- **FR-027**: El detalle de deseos, vinculaciones, evidencia, confianza y limitaciones MUST ser inspeccionable y corregible fuera del texto efimero del chat.
- **FR-028**: Las trayectorias conversacionales de aceptacion MUST declarar estado inicial, turnos, actos esperados, cambios durables, estado final y comportamientos prohibidos.
- **FR-029**: Los invariantes criticos de estado, seguridad, equidad y mutaciones MUST pasar en todos los casos de aceptacion.
- **FR-030**: La transcripcion que origino esta feature y sus variantes MUST formar parte de la regresion multi-turno y terminar sin loops ni escrituras sobre anuncios equivocados.

### Key Entities

- **Radar**: busqueda durable y versionada, potencialmente parcial, con alcance, filtros, preferencias y estado operativo.
- **Deseo expresado**: declaracion completa de la persona, ligada a un radar y conservada aun cuando no sea evaluable.
- **Vinculacion de criterio**: interpretacion versionada del deseo hacia capacidades estructuradas o semanticas, o hacia un estado no evaluable.
- **Hecho de preferencia**: representacion estructurada vigente de una preferencia computable con importancia, confianza, fuente y estado.
- **Criterio compilado**: condicion validada consumida por filtrado u ordenamiento, con referencias a su deseo, vinculacion y evidencia.
- **Contexto conversacional activo**: referencias verificables necesarias para interpretar el siguiente turno sin depender de adivinanzas.
- **Hipotesis de preferencia**: inferencia de baja autoridad nacida de señales pasivas o patrones entre radares; no modifica criterios por si sola.
- **Trayectoria conversacional**: caso de evaluacion multi-turno que verifica evolucion de estado, efectos y prohibiciones.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Una persona sin radar termina su primer intercambio significativo con un radar durable que conserva todos los deseos expresados, sin completar antes un formulario.
- **SC-002**: El 100% de los deseos fuera del catalogo en la suite de aceptacion se conserva con estado visible y ninguno se rechaza mediante una lista cerrada de preferencias permitidas.
- **SC-003**: El 100% de las correcciones explicitas se refleja en el estado mostrado durante el turno siguiente y conserva trazabilidad del estado anterior.
- **SC-004**: La suite critica registra cero preguntas repetidas cuya respuesta siga vigente y cero mutaciones sobre el radar, anuncio o accion equivocados.
- **SC-005**: El 100% de los invariantes de estado, seguridad, equidad y mutaciones pasa en todas las ejecuciones de aceptacion.
- **SC-006**: Al menos el 95% de las trayectorias conversacionales completas alcanza el estado final esperado y ninguna familia critica queda por debajo del 90%.
- **SC-007**: La transcripcion de regresion termina con alcance geografico abierto, conserva Nuñez como decision previa reemplazada y mantiene luminosidad, cercania al subte, cocina grande, cafes para home office y cercania a parques, sin repetir la pregunta por zona.
- **SC-008**: En una prueba con al menos ocho personas representativas, al menos el 80% completa sin ayuda las tareas de crear, refinar, corregir y recuperar un radar; la facilidad mediana reportada es al menos 6 sobre 7 y hay cero loops irrecuperables.
- **SC-009**: La persona recibe una señal visible de progreso en menos de un segundo y el 95% de las respuestas conversacionales normales finaliza en menos de cinco segundos; los trabajos mas largos mantienen estado visible sin bloquear el chat.
- **SC-010**: El 100% de los radares sin resultados por filtros duros recibe una explicacion del bloqueo y al menos una relajacion concreta sin cambios silenciosos.
- **SC-011**: Ninguna preferencia sustentada solo por evidencia semantica se convierte en filtro duro ni decide por si sola la inclusion de candidatos.
- **SC-012**: Ningun resultado calculado para una version obsoleta reemplaza al resultado vigente durante las trayectorias con cambios consecutivos.

## Assumptions

- La beta sigue enfocada en alquileres residenciales en CABA y reutiliza identidad, listings, radares, scoring, feedback y evidencia existentes.
- El chat es la interfaz primaria para expresar intencion, pero el radar y su estado detallado siguen visibles y editables en superficies estructuradas.
- El ordenamiento final, los filtros duros y las decisiones de notificacion siguen siendo deterministas, versionados y auditables.
- Las capacidades compartidas se promueven al catalogo solo cuando son recurrentes, evaluables, cuentan con evidencia suficiente y superan validacion de calidad.
- La personalizacion entre radares se limita a sugerencias hasta que la persona las adopte en el radar activo.
- El rediseño de importacion de listings, notificaciones, identidad y fuentes urbanas queda fuera de alcance salvo por los contratos necesarios para consumir su evidencia existente.
- No se crea una clase distinta de criterio por persona; la diversidad personal se representa mediante deseos y vinculaciones versionadas.

## Out of Scope

- Garantizar que todo deseo arbitrario sea evaluable desde el primer dia.
- Crear un concepto compartido por cada frase o cada persona.
- Permitir que un modelo generativo decida filtros duros o ranking final.
- Redisenar las fuentes de listings, el pipeline Bronze/Silver o las notificaciones proactivas completas.
- Aplicar preferencias globales silenciosas a todos los radares de una persona.
- Reemplazar lista, mapa, detalle o edicion estructurada por una interfaz exclusivamente conversacional.
