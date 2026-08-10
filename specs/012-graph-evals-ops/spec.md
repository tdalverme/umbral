# Feature Specification: Evals, costos y operacion del agente

**Feature Branch**: `012-graph-evals-ops`

**Created**: 2026-08-10

**Status**: Draft

**Input**: User description: "Arranquemos con la especificacion de la epica H4.4 - Evals, costos y operacion del backlog, con alcance exacto UM-H4-026 a UM-H4-030."

## Clarifications

### Session 2026-08-10

- Q1 (alcance): Las notas de aceptacion de H4.1, H4.2 y H4.3 difieren a H4.4 el "ADR de proveedor de modelo", que no aparece como item de la epica. ¿Se incluye como entregable de este incremento? → A: Se incluye. El ADR cierra el diferido asignado a H4.4 en tres notas de aceptacion (misma convencion que H4.3 al cerrar la composicion de produccion diferida de H4.1); es condicion para fijar presupuestos realistas y alimenta el dashboard, y queda vinculado al harness como entregable verificable.
- Q2 (gate de regresiones): ¿Como bloquean las regresiones de eval a una release del graph? → A: Gate estricto en señales deterministas y umbrales en las LLM-dependientes. La seleccion de tool, la validez de argumentos, el grounding, el cumplimiento de confirmacion y la clase de outcome bloquean ante cualquier desvio (convencion de gate estricto de H3.4, 0 tolerancia); el costo y la latencia usan umbrales definidos por politica versionada. Evita gates fragiles sobre comportamiento LLM no determinista.
- Q3 (presupuesto agotado): ¿Que pasa cuando una sesion o usuario agota su presupuesto? → A: Bloqueo duro recuperable. La ejecucion se detiene o rechaza con estado tipado y mensaje claro que declara el limite y su ventana de politica (por ejemplo, reset diario) y las acciones disponibles; el usuario puede retomar al reiniciarse la ventana o con una accion explicita. 0 degradacion de calidad del modelo: no se cambia el proveedor ni se reduce contexto para estirar el presupuesto.
- Q4 (fidelidad de los evals): ¿Con que fidelidad de modelo se ejecutan los evals del graph? → A: Hibrido. El harness local y CI (gate de regresiones) corren con un adapter determinista simulado: reproducible, 0 costo y 0 dependencia de proveedor, cumpliendo FR-007 en el gate. Los evals contra el proveedor real (el elegido en el ADR) corren en un flujo separado, programado y con un presupuesto de eval acotado por politica, para validar el comportamiento con el modelo de produccion sin flakiness en el gate.
- Q5 (tamano del dataset golden): ¿Cuantos casos curados debe tener como minimo el dataset golden de conversaciones? → A: Al menos 3 casos por familia (21 total en el dataset inicial), versionado y ampliable en incrementos posteriores; la familia de injection/rechazo seguro admite mas casos que el resto por ser critica.
- Q6 (activacion de releases): ¿Quien activa una release como vigente cuando su gate pasa? → A: Hibrida. La activacion es automatica cuando el cambio es de codigo, topologia o schemas; cuando el cambio toca prompts o modelos, la activacion requiere aprobacion explicita de un operador con el reporte de eval como evidencia. El control humano se concentra en los cambios generativos, los de mayor riesgo de regresion no cubierta por el dataset.

## Operational Definitions

- **Dataset golden de conversaciones**: conjunto versionado y curado de casos de conversacion (transcripcion + contexto de radar/listing + expectativa) revisado por producto, que cubre onboarding, cambios ambiguos, explicacion, comparacion, feedback, injection y rechazo seguro. Cada caso define el comportamiento esperado: tools a seleccionar con sus argumentos, confirmaciones requeridas, restricciones de grounding y clase de outcome; 0 PII.
- **Eval del graph**: evaluacion automatica y repetible de un graph run contra las expectativas del dataset golden: seleccion de tool, validez de argumentos, grounding (toda afirmacion cita evidencia persistida), cumplimiento de confirmacion (0 efectos sin confirmacion), clase de outcome y costo por caso. Produce un reporte versionado con metricas agregadas y por caso.
- **Gate de regresiones de eval**: regla determinista que decide si una release del graph pasa o bloquea comparando su reporte de eval contra la release actual sobre el mismo dataset golden. Es estricto en señales deterministas (seleccion de tool, argumentos, grounding, confirmacion y outcome: cualquier desvio bloquea) y usa umbrales de politica versionada para costo y latencia.
- **Release del graph**: bundle versionado e inmutable que registra las versiones de prompts, modelos, schemas y topologia/nodos que definen un graph run; cada run referencia su release y las releases previas no se mutan (0 reescrituras de runs previos).
- **Revert de release**: mecanismo por el cual los runs nuevos usan la release anterior a la vigente, sin mutar runs ya ejecutados; permite comparar dos releases (A/B sobre el dataset golden) y volver atras de forma controlada.
- **Presupuesto (budget)**: limite versionado de tokens, calls de tools, concurrencia y costo por usuario y por sesion dentro de una ventana de politica; al agotarse se aplica bloqueo duro recuperable: la ejecucion se detiene o rechaza con estado tipado y mensaje claro, y el usuario retoma al reiniciarse la ventana o con una accion explicita, sin degradar la calidad del modelo.
- **Rate limit**: limite de concurrencia y volumen que protege la infraestructura y el costo agregado; se comunica al usuario con estados tipados y accionables.
- **Dashboard del agente**: vista operativa interna (no superficie de producto para usuarios) que agrega metricas de los graph/tool runs ya registrados: latencia, errores, tool success, interrupts, tokens, costo y regresiones de eval.
- **ADR de proveedor de modelo**: registro de decision arquitectonica que compara alternativas de proveedor de modelo con criterios explicitos (costo, calidad, latencia, privacidad, operabilidad) y documenta la decision, sus riesgos y el monitoreo acordado.

## Review and Measurement Protocol

- La puerta de salida de H4.4 cierra el hito `conversational-radar` (UM-H4-001 a UM-H4-030): el graph queda con dataset golden de conversaciones, evals automatizados y gated, prompts/modelos/releases versionables y revertibles, presupuestos y rate limits aplicados con limites recuperables comunicados, y dashboard operativo del agente.
- El dataset golden se verifica confirmando que cubre las 7 familias acordadas con producto (onboarding, cambios ambiguos, explicacion, comparacion, feedback, injection y rechazo seguro) con al menos 3 casos por familia (21 casos en el dataset inicial), que es versionado y consultable, que 0 casos contienen PII y que la revision de producto de cada caso queda registrada con evidencia.
- Los evals se verifican corriendo el suite completo sobre el dataset golden: el 100% de los casos se evalua, las metricas se reportan por caso y agregadas con la version de la release evaluada, y el gate de regresiones es estricto en señales deterministas (seleccion de tool, argumentos, grounding, confirmacion y outcome: cualquier desvio bloquea) con umbrales de politica versionada para costo y latencia; los evals no dependen de estado mutable entre corridas (0 resultados no reproducibles). El gate corre con un adapter determinista simulado (0 costo, reproducible); los evals contra el proveedor real corren en un flujo separado, programado y con presupuesto de eval acotado por politica.
- Las releases se verifican confirmando que cada release registra versiones de prompts/modelos/schemas/topologia, que los runs previos no se mutan al crear o revertir releases (0 reescrituras), que la comparacion de dos releases sobre el mismo dataset golden produce reportes comparables, y que la activacion sigue la regla hibrida: automatica para codigo/topologia/schemas y con aprobacion explicita de operador para prompts/modelos.
- Los presupuestos y rate limits se verifican probando el comportamiento al alcanzar cada limite (tokens, tools, concurrencia, costo) con usuarios/sesiones reales y manipulados: el limite se aplica en el 100% de los casos, el bloqueo duro es recuperable (estado tipado, ventana de politica y accion explicita), la comunicacion al usuario es clara, y 0 ejecuciones exceden el presupuesto ni degradan la calidad del modelo.
- El dashboard se verifica contrastando sus metricas contra los graph/tool runs registrados (H4.1/H4.2): las cifras de latencia, errores, tool success, interrupts, tokens y costo coinciden con los registros fuente y las regresiones de eval aparecen vinculadas a sus releases.
- El ADR se verifica como documento versionado que documenta alternativas comparadas con criterios explicitos (costo, calidad, latencia, privacidad, operabilidad), decision, riesgos y monitoreo, registrado en el repo y referenciado por el harness.
- Los checks se integran al harness local (`scripts/check.ps1`) con la convencion de los incrementos previos (harness dedicado `check-evals.ps1`), y el incremento no cambia matching, scoring, ingesta ni el comportamiento conversacional salvo a traves de releases versionadas.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Dataset golden de conversaciones (Priority: P0)

Como equipo de producto y desarrollo, quiero un dataset golden de conversaciones curado y versionado, para que cada mejora del chat tenga una referencia objetiva de comportamiento esperado.

**Why this priority**: Es la base de los evals (UM-H4-027) y de las releases (UM-H4-028): sin expectativas revisadas no hay regresiones medibles ni confianza para cambiar prompts o modelos.

**Independent Test**: Se revisa el dataset: el 100% de los casos cubre una familia acordada con producto, cada caso define tools/argumentos/confirmaciones/grounding/outcome esperados, la revision de producto esta registrada y 0 casos contienen PII.

**Acceptance Scenarios**:

1. **Given** la curaduria de casos, **When** se incorpora un caso, **Then** pertenece a una de las 7 familias (onboarding, cambios ambiguos, explicacion, comparacion, feedback, injection, rechazo seguro) y define el comportamiento esperado completo: tools a seleccionar con argumentos validos, confirmaciones requeridas, restricciones de grounding y clase de outcome.
2. **Given** un caso con cambios ambiguos, **When** el caso se registra, **Then** la expectativa incluye la aclaracion esperada antes de cualquier propuesta (H4.3); 0 expectativas con efectos sin confirmacion.
3. **Given** un caso de injection o rechazo seguro, **When** el caso se registra, **Then** la expectativa incluye la respuesta de rechazo que declara el limite; 0 ejecuciones de tools no permitidas.
4. **Given** el dataset completo, **When** se versiona, **Then** es consultable, inmutable en su version y cada caso registra la revision de producto con responsable y fecha.
5. **Given** cualquier caso, **When** se revisa su contenido, **Then** 0 PII y 0 datos de radares reales: el dataset se construye con datos sinteticos o redactados del dataset controlado de beta.

---

### User Story 2 - Evals automatizados del graph (Priority: P0)

Como equipo de desarrollo, quiero evals automatizados que midan seleccion de tool, argumentos, grounding, confirmacion, outcome y costo por caso, para detectar regresiones del chat antes de exponer cambios a usuarios.

**Why this priority**: Es el control de calidad del radar conversacional: sin evals reproducibles, cambiar un prompt o un modelo es un salto al vacio sobre el unico componente generativo del producto.

**Independent Test**: Se corre el suite completo sobre el dataset golden y se verifica que el 100% de los casos produce metricas de seleccion de tool, argumentos, grounding, confirmacion, outcome y costo, con reporte versionado y sin dependencia de estado entre corridas.

**Acceptance Scenarios**:

1. **Given** un caso del dataset golden, **When** se ejecuta el graph, **Then** la evaluacion mide la tool seleccionada y sus argumentos contra la expectativa, y el resultado queda registrado por caso con la release evaluada.
2. **Given** una respuesta del graph, **When** se evalua grounding, **Then** se verifica que el 100% de las afirmaciones de producto cita evidencia persistida y que 0 afirmaciones se completan sin evidencia (H4.3/H3.4).
3. **Given** un caso con mutacion propuesta, **When** se evalua confirmacion, **Then** se verifica que 0 efectos ocurren sin confirmacion explicita y que la secuencia de confirmacion coincide con la expectativa.
4. **Given** cualquier caso, **When** se evalua, **Then** se reporta la clase de outcome esperada (completado, aclaracion, rechazo seguro, fallo) y el costo del caso (uso registrado de H4.1 contra la tabla de precios de la release).
5. **Given** dos corridas del mismo suite, **When** se comparan, **Then** los resultados son reproducibles (0 diferencias no explicadas) y el reporte incluye metricas agregadas: accuracy de seleccion, validez de argumentos, cobertura de grounding, cumplimiento de confirmacion, distribucion de outcomes y costo promedio por caso.

---

### User Story 3 - Releases versionadas y revertibles (Priority: P0)

Como equipo de desarrollo, quiero que cada cambio de prompts, modelos, schemas o nodos sea una release versionada, comparable y revertible, para que ninguna mejora del chat se haga sin trazabilidad ni posibilidad de volver atras.

**Why this priority**: Es la aplicacion al graph de la regla de "prompts, modelos, scores y extracciones versionados" de la constitucion; sin releases no hay evals comparables ni rollback seguro.

**Independent Test**: Se crea una release nueva, se compara contra la anterior sobre el dataset golden, se ejecuta el gate de regresiones y se revierte; se verifica que los runs previos no se mutan en ningun momento (0 reescrituras).

**Acceptance Scenarios**:

1. **Given** un cambio de prompt, modelo, schema o topologia, **When** se empaqueta, **Then** la release registra las versiones de todos sus componentes y queda inmutable: 0 ediciones posteriores a la creacion.
2. **Given** una release creada, **When** se ejecutan runs, **Then** cada run referencia la release que lo produjo y los runs previos conservan su release original (0 reescrituras de runs previos).
3. **Given** dos releases, **When** se comparan, **Then** ambas corren el mismo dataset golden y el reporte muestra diferencias por caso y agregadas (seleccion, argumentos, grounding, confirmacion, outcome, costo).
4. **Given** una release candidata, **When** pasa el gate de regresiones (señales deterministas sin desvios y costo/latencia dentro de umbrales de politica), **Then** queda activa para los runs nuevos de forma automatica si el cambio es de codigo/topologia/schemas, o con aprobacion explicita de un operador con el reporte de eval si el cambio toca prompts o modelos; si el gate falla, **Then** se rechaza y los runs nuevos siguen en la release vigente anterior.
5. **Given** una release activa con problemas, **When** se revierte, **Then** los runs nuevos usan la release anterior, los runs ya ejecutados no se tocan y la reversion queda registrada con motivo y responsable.

---

### User Story 4 - Presupuestos y rate limits (Priority: P0)

Como usuario y como operador, quiero que el uso del chat tenga limites de tokens, tools, concurrencia y costo por usuario y sesion, para que el costo sea predecible y los limites se comuniquen de forma clara y recuperable.

**Why this priority**: El chat consume un recurso pagado por token; sin presupuestos, un uso anormal o un bug puede generar costos inaceptables. Los limites son la frontera operativa del costo de beta.

**Independent Test**: Se ejercitan los limites (tokens, tools, concurrencia, costo) con sesiones reales y manipuladas y se verifica que el 100% de los excesos se detiene, comunica y recupera segun politica, con 0 ejecuciones que exceden el presupuesto.

**Acceptance Scenarios**:

1. **Given** una sesion o usuario dentro de presupuesto, **When** opera el chat, **Then** el consumo se registra (tokens, tools, costo) contra su presupuesto y 0 usos de otros usuarios afectan el suyo.
2. **Given** una sesion cercana al limite, **When** el consumo avanza, **Then** el usuario recibe una advertencia clara antes de agotar el presupuesto, sin interrumpir la conversacion en curso.
3. **Given** un presupuesto agotado, **When** el usuario intenta continuar, **Then** se aplica bloqueo duro recuperable: la ejecucion se detiene o rechaza con estado tipado y un mensaje claro que declara el limite, la ventana de politica (por ejemplo, reset diario) y las acciones disponibles (retomar al reiniciarse la ventana o accion explicita); 0 degradacion de calidad del modelo y 0 silencio sobre la causa.
4. **Given** una sesion con ejecucion en curso, **When** otra solicitud excede la concurrencia permitida, **Then** se rechaza con estado tipado (H4.1: 0 ejecuciones paralelas) y el usuario puede esperar o reintentar.
5. **Given** cualquier exceso de limite, **When** se registra, **Then** queda un evento auditable (usuario/sesion, limite, valor alcanzado, accion) sin exponer PII innecesaria, y los valores de los presupuestos son parametros de politica versionados.

---

### User Story 5 - Dashboard del agente (Priority: P1)

Como operador, quiero ver en un solo lugar la latencia, errores, tool success, interrupts, tokens, costo y regresiones de eval del agente, para operar la beta y detectar problemas antes que los usuarios.

**Why this priority**: Es la vista operativa que cierra el ciclo de evals y costos; es P1 porque no bloquea el funcionamiento del chat pero es necesaria para operar con confianza la beta.

**Independent Test**: Se generan runs y evals conocidos y se verifica que el dashboard muestra las mismas cifras que los registros fuente (H4.1/H4.2) y las regresiones vinculadas a sus releases.

**Acceptance Scenarios**:

1. **Given** graph y tool runs registrados, **When** se consulta el dashboard, **Then** muestra latencia, errores, tool success, interrupts, tokens y costo agregados y por sesion, coincidiendo con los registros fuente.
2. **Given** un suite de eval ejecutado, **When** se consulta el dashboard, **Then** las regresiones de eval aparecen vinculadas a la release evaluada con su resultado de gate.
3. **Given** datos sensibles en los registros, **When** se agregan, **Then** el dashboard expone 0 PII: solo agregados y metadatos permitidos.
4. **Given** el dashboard, **When** lo usa un operador, **Then** es una vista interna de solo lectura: 0 acciones de mutacion desde la UI y 0 acceso a datos de usuarios no agregados.

---

### User Story 6 - ADR de proveedor de modelo (Priority: P0)

Como equipo, quiero una decision documentada de proveedor de modelo con alternativas comparadas, para que la eleccion sea auditable y sus riesgos tengan monitoreo acordado.

**Why this priority**: Es un diferido de H4.1/H4.2/H4.3 asignado a H4.4 en las notas de aceptacion; el proveedor define costo, calidad y latencia del chat y condiciona los presupuestos y el dashboard.

**Independent Test**: Se verifica que el documento versionado compara alternativas con criterios explicitos (costo, calidad, latencia, privacidad, operabilidad), registra la decision, los riesgos y el monitoreo, y queda referenciado por el harness.

**Acceptance Scenarios**:

1. **Given** alternativas de proveedor, **When** se comparan, **Then** el ADR evalua costo, calidad, latencia, privacidad y operabilidad con evidencia de los evals del dataset golden.
2. **Given** la decision, **When** se documenta, **Then** registra la alternativa elegida, las descartadas con su razon, los riesgos y el monitoreo acordado (que alimenta presupuestos y dashboard).
3. **Given** el ADR aprobado, **When** se integra, **Then** el repo lo referencia y los parametros de modelo de las releases y los presupuestos se alinean con la decision.

### Edge Cases

- Caso golden con transcripcion ambigua entre dos intenciones: la expectativa exige aclaracion; 0 expectativas con adivinanza.
- Caso de injection exitoso si el graph lo ejecuta: el eval lo reporta como fallo critico y el gate bloquea la release.
- Rechazo seguro: el graph declara el limite y 0 tools no permitidas se ejecutan; el eval verifica ambas cosas.
- Eval con resultado no reproducible (flakiness del modelo real): en el flujo de evals con proveedor real se reintenta segun politica y se reporta la varianza; 0 resultados no reproducibles pasan el gate (el gate corre con adapter simulado y es determinista).
- Release creada y luego detectada defectuosa: se revierte sin mutar runs previos y la reversion queda auditada con motivo.
- Revert durante runs en vuelo: los runs iniciados terminan con su release original; los nuevos usan la release revertida.
- Presupuesto agotado a mitad de una ejecucion: la ejecucion en curso termina su turno actual y las solicitudes siguientes se bloquean con estado tipado y mensaje claro; el presupuesto se recupera al reiniciarse la ventana de politica o con accion explicita (bloqueo duro recuperable).
- Concurrencia excedida: rechazo tipado sin cola oculta; 0 ejecuciones paralelas (H4.1).
- Costo anormal en un solo run (bug o uso adversarial): el run se registra con su costo y el presupuesto de usuario/sesion lo absorbe; el dashboard lo hace visible para operacion.
- Dataset golden desactualizado frente a cambios de producto: la actualizacion del dataset es versionada y requiere revision de producto.
- Dashboard con datos desactualizados: indica la antiguedad de los datos; 0 cifras presentadas como en vivo sin marca de tiempo.
- 0 PII en dataset golden, evals y dashboard en el 100% de los casos.

## Requirements *(mandatory)*

### Functional Requirements

#### Dataset golden de conversaciones (UM-H4-026)

- **FR-001**: El sistema MUST mantener un dataset golden de conversaciones versionado e inmutable por version, con casos de las 7 familias acordadas con producto: onboarding, cambios ambiguos, explicacion, comparacion, feedback, injection y rechazo seguro. El dataset inicial MUST tener al menos 3 casos por familia (21 casos total), y las versiones posteriores MUST ampliarlo de forma versionada sin reducir el minimo.
- **FR-002**: Cada caso golden MUST definir la expectativa completa de comportamiento: tools a seleccionar con argumentos validos, confirmaciones requeridas (0 efectos sin confirmacion, H4.3), restricciones de grounding y clase de outcome (completado, aclaracion, rechazo seguro, fallo).
- **FR-003**: El dataset golden MUST registrar la revision de producto de cada caso (responsable y fecha) y MUST contener 0 PII: los casos se construyen con datos sinteticos o redactados del dataset controlado de beta.
- **FR-004**: Los casos de cambios ambiguos MUST incluir en su expectativa la aclaracion previa a cualquier propuesta; los casos de injection y rechazo seguro MUST incluir la respuesta que declara el limite y la ausencia de tools no permitidas.

#### Evals automatizados del graph (UM-H4-027)

- **FR-005**: El sistema MUST ejecutar evals automatizados del graph sobre el dataset golden midiendo por caso: seleccion de tool, validez de argumentos, grounding (100% de afirmaciones de producto con evidencia persistida, 0 completaciones sin evidencia), cumplimiento de confirmacion, clase de outcome y costo por caso.
- **FR-006**: Cada resultado de eval MUST quedar registrado con la release evaluada, la version del dataset golden y metricas agregadas (accuracy de seleccion, validez de argumentos, cobertura de grounding, cumplimiento de confirmacion, distribucion de outcomes y costo promedio por caso).
- **FR-007**: Los evals MUST ser reproducibles: dos corridas del mismo suite sobre la misma release producen el mismo reporte, o las diferencias quedan explicadas por politica de reintento y varianza registrada. El gate de regresiones del harness y CI MUST correr con un adapter determinista simulado (0 costo, 0 dependencia de proveedor); los evals con el modelo real MUST correr en un flujo separado, programado y con presupuesto de eval acotado por politica.
- **FR-008**: El gate de regresiones de eval MUST evaluar cada release candidata contra la release vigente sobre el mismo dataset golden y MUST ser estricto en señales deterministas (seleccion de tool, validez de argumentos, grounding, cumplimiento de confirmacion y clase de outcome: cualquier desvio bloquea, 0 tolerancia, convencion de H3.4) con umbrales de politica versionada para costo y latencia; el reporte del gate MUST quedar vinculado a la release evaluada.

#### Releases versionadas y revertibles (UM-H4-028)

- **FR-009**: El sistema MUST empaquetar cada cambio de prompts, modelos, schemas o topologia como una release versionada e inmutable que registra las versiones de todos sus componentes; 0 ediciones posteriores a la creacion.
- **FR-010**: Cada graph run MUST referenciar la release que lo produjo, y crear o revertir releases MUST NO mutar runs ya ejecutados (0 reescrituras de runs previos).
- **FR-011**: El sistema MUST permitir comparar dos releases sobre el mismo dataset golden con reportes por caso y agregados, y MUST permitir revertir la release activa para que los runs nuevos usen la release anterior, registrando la reversion con motivo y responsable. La activacion de una release que paso el gate MUST ser automatica cuando el cambio es de codigo, topologia o schemas, y MUST requerir aprobacion explicita de un operador (con el reporte de eval como evidencia) cuando el cambio toca prompts o modelos.

#### Presupuestos y rate limits (UM-H4-029)

- **FR-012**: El sistema MUST aplicar presupuestos por usuario y por sesion de tokens, calls de tools, concurrencia y costo dentro de una ventana de politica versionada, y MUST registrar el consumo de cada run contra su presupuesto con 0 acceso a presupuestos ajenos.
- **FR-013**: Antes de agotar un presupuesto, el usuario MUST recibir una advertencia clara sin interrumpir la conversacion en curso.
- **FR-014**: Al agotarse un presupuesto, el sistema MUST aplicar bloqueo duro recuperable: la ejecucion se detiene o rechaza con estado tipado y mensaje claro que declara el limite, la ventana de politica y las acciones disponibles (retomar al reiniciarse la ventana o accion explicita), y MUST NO degradar la calidad del modelo (0 cambio de proveedor ni reduccion de contexto para estirar el presupuesto).
- **FR-015**: El sistema MUST aplicar rate limits de concurrencia y volumen: una solicitud que excede la concurrencia permitida MUST rechazarse con estado tipado y accionable (0 ejecuciones paralelas, H4.1) y 0 colas ocultas.
- **FR-016**: Todo exceso de limite MUST quedar registrado como evento auditable (usuario/sesion, limite, valor alcanzado, accion) sin PII innecesaria, y los valores de presupuestos MUST ser parametros de politica versionados.

#### Dashboard del agente (UM-H4-030, P1)

- **FR-017**: El sistema MUST exponer una vista operativa interna del agente que agregue los registros fuente (H4.1/H4.2): latencia, errores, tool success, interrupts, tokens y costo, coincidiendo con los registros de graph/tool runs.
- **FR-018**: El dashboard MUST mostrar las regresiones de eval vinculadas a la release evaluada con su resultado de gate, MUST indicar la antiguedad de sus datos y MUST exponer 0 PII (solo agregados y metadatos permitidos).
- **FR-019**: El dashboard MUST ser de solo lectura para operadores: 0 acciones de mutacion desde la vista y 0 acceso a datos de usuarios no agregados.

#### Transversal

- **FR-020**: El incremento MUST integrar su harness de verificacion en `scripts/check.ps1` con la convencion de los incrementos previos (harness dedicado), cubriendo dataset, evals, gate, releases, presupuestos y dashboard, sin regresiones en las suites previas de H4.
- **FR-021**: El incremento MUST NO cambiar matching, scoring, ingesta ni el comportamiento conversacional salvo a traves de releases versionadas con sus evals.
- [**FR-022** — ADR proveedor de modelo (diferido H4.1/H4.2/H4.3 asignado a H4.4)]: El incremento MUST producir el ADR de proveedor de modelo como documento versionado que compara alternativas con criterios explicitos (costo, calidad, latencia, privacidad, operabilidad), registra la decision, los riesgos y el monitoreo, y queda referenciado por el repo y el harness.

### Key Entities

- **GoldenConversationCase**: caso curado del dataset golden (familia, transcripcion, contexto, expectativa de tools/argumentos/confirmaciones/grounding/outcome, revision de producto); versionado e inmutable, 0 PII.
- **EvalReport / EvalRun**: resultado versionado de evaluar una release contra una version del dataset golden: metricas por caso y agregadas (seleccion, argumentos, grounding, confirmacion, outcome, costo) con resultado de gate.
- **GraphRelease**: bundle versionado e inmutable de versiones de prompts, modelos, schemas y topologia; cada graph run referencia la suya y las releases previas no se mutan.
- **PromptVersion / ModelVersion**: versiones individuales de los componentes que una release empaqueta y que los graph runs registran.
- **BudgetPolicy / BudgetConsumption**: limites versionados (tokens, tools, concurrencia, costo) por usuario/sesion en ventana de politica y el consumo registrado por run; alimenta advertencias, bloqueos y eventos auditables.
- **OpsDashboardReport**: agregado operativo interno de los graph/tool runs registrados (H4.1/H4.2) y de los resultados de eval, de solo lectura y sin PII.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Dataset golden de conversaciones | UM-H4-026 |
| User Story 2 - Evals automatizados del graph | UM-H4-027 |
| User Story 3 - Releases versionadas y revertibles | UM-H4-028 |
| User Story 4 - Presupuestos y rate limits | UM-H4-029 |
| User Story 5 - Dashboard del agente | UM-H4-030 |
| User Story 6 - ADR de proveedor de modelo | Diferido H4.1/H4.2/H4.3 asignado a H4.4 (resuelto: se incluye) |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H4-026 | FR-001, FR-002, FR-003, FR-004 | US1.1-US1.5, SC-001 |
| UM-H4-027 | FR-005, FR-006, FR-007, FR-008 | US2.1-US2.5, SC-002 |
| UM-H4-028 | FR-009, FR-010, FR-011 | US3.1-US3.5, SC-003 |
| UM-H4-029 | FR-012, FR-013, FR-014, FR-015, FR-016 | US4.1-US4.5, SC-004 |
| UM-H4-030 | FR-017, FR-018, FR-019 | US5.1-US5.4, SC-005 |
| ADR proveedor (diferido) | FR-022 | US6.1-US6.3, SC-006 |
| Transversal (todos) | FR-020, FR-021 | SC-007 |

## Constitution Alignment *(mandatory)*

- **Persistent radar as product truth**: los evals y releases protegen el comportamiento del chat sobre objetos persistentes (propuestas, feedback, explicaciones, runs); 0 decisiones de calidad que viven solo en reportes efimeros. Sustenta el principio I.
- **Auditable deterministic matching**: el gate de regresiones y la seleccion de herramientas se validan contra expectativas versionadas; los evals verifican que 0 ranking ni efectos finales provienen de lo generativo (H4.2/H4.3). Sustenta el principio II.
- **Layered dependency direction**: evals, releases, presupuestos y dashboard operan sobre los contratos y registros existentes (H4.1/H4.2/H4.3); 0 acceso nuevo y libre a datos desde el agente y 0 superficie nueva de usuario en este incremento. Sustenta el principio III.
- **Minimal verifiable change**: el incremento se limita a UM-H4-026 a UM-H4-030 mas el diferido asignado a H4.4 (ADR de proveedor de modelo, resuelto en clarificacion Q1); 0 cambios de matching/scoring y 0 features especulativas; toda verificacion por harness con la convencion de los incrementos previos. Sustenta el principio IV.
- **Data lineage, observability and trust**: todo run, release y eval queda registrado con versiones y correlacion; el costo y el uso se derivan de los registros de H4.1/H4.2 y el dashboard expone 0 PII. Sustenta el principio V.
- **Versioned prompts, models, schemas and releases**: la regla "prompts, modelos, scores y extracciones versionados" se extiende a releases completas del graph, comparables y revertibles sin mutar runs previos. Sustenta los principios II y V.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El dataset golden cubre el 100% de las 7 familias acordadas con al menos 3 casos por familia (21 casos en el dataset inicial), cada caso define tools/argumentos/confirmaciones/grounding/outcome esperados, la revision de producto esta registrada y 0 casos contienen PII.
- **SC-002**: El suite de evals evalua el 100% de los casos golden con metricas de seleccion de tool, argumentos, grounding, confirmacion, outcome y costo por caso; el 100% de los resultados es reproducible y el gate de regresiones es estricto en señales deterministas (cualquier desvio bloquea) con umbrales de politica para costo y latencia.
- **SC-003**: El 100% de los cambios de prompts/modelos/schemas/topologia se empaqueta como release inmutable, el 100% de los runs referencia su release, 0 runs previos se mutan al crear/revertir releases y la comparacion y reversion de releases quedan auditadas.
- **SC-004**: El 100% de los excesos de presupuesto (tokens, tools, concurrencia, costo) se aplica como bloqueo duro recuperable con estado tipado, mensaje claro y ventana de politica; 0 ejecuciones exceden el presupuesto, 0 accesos a presupuestos ajenos y 0 degradacion de calidad del modelo.
- **SC-005**: El dashboard muestra latencia, errores, tool success, interrupts, tokens y costo coincidentes con los registros fuente y las regresiones de eval vinculadas a su release; 0 PII y 0 acciones de mutacion desde la vista.
- **SC-006**: El ADR de proveedor de modelo compara alternativas con criterios explicitos (costo, calidad, latencia, privacidad, operabilidad) y documenta decision, riesgos y monitoreo, versionado y referenciado por el repo y el harness.
- **SC-007**: El harness del incremento corre en `scripts/check.ps1` sin regresiones en las suites previas de H4 y el comportamiento del chat solo cambia a traves de releases con evals.

## Assumptions

- El alcance incluye exactamente UM-H4-026 a UM-H4-030 (Epica H4.4 - Evals, costos y operacion), que cierra el hito `conversational-radar` (UM-H4-001 a UM-H4-030), mas el diferido explicitamente asignado a H4.4 en las notas de aceptacion de H4.1/H4.2/H4.3: el ADR de proveedor de modelo (resuelto en clarificacion: se incluye como entregable vinculado al harness). El "gate completo desde checkout limpio en CI" diferido en los incrementos previos queda fuera de este alcance (sigue como seguimiento global).
- Depende de la maquinaria existente y NO la reimplementa: registros de graph/tool runs con version, latencia, estado, errores, uso y correlacion (H4.1); uso de tokens del adapter de modelo (H4.1); tools con contrato comun y permisos (H4.2); comportamiento conversacional de H4.3 (intencion, aclaraciones, HITL, grounding, contratos); dataset golden de recomendaciones y gate de regresiones de scoring (H3.4) como convencion de referencia.
- El dataset golden de conversaciones se construye sobre el dataset controlado de beta con datos sinteticos o redactados; 0 PII y 0 radares reales.
- El gate de regresiones es estricto en señales deterministas (seleccion de tool, argumentos, grounding, confirmacion y outcome: cualquier desvio bloquea, 0 tolerancia, convencion de H3.4) y usa umbrales de politica versionada para costo y latencia; los reintentos de eval y las politicas de varianza tambien son parametros de politica versionados (resuelto en clarificacion Q2).
- El presupuesto agotado aplica bloqueo duro recuperable: estado tipado, mensaje claro con ventana de politica y acciones disponibles, y 0 degradacion de calidad del modelo; los valores de tokens/tools/concurrencia/costo y las ventanas se definen en el plan (resuelto en clarificacion Q3).
- El dashboard es una vista operativa interna de solo lectura; 0 superficie de producto nueva para usuarios en este incremento.
- El idioma de copy, casos y registros es espanol (CABA).
- [RESUELTO Q1 - opcion A]: el ADR de proveedor de modelo se incluye en el incremento: cierra el diferido asignado a H4.4 en las notas de aceptacion de H4.1/H4.2/H4.3, con la misma convencion que H4.3 al cerrar la composicion de produccion diferida de H4.1; queda vinculado al harness y condiciona los presupuestos y el dashboard.
- [RESUELTO Q2 - opcion A]: el gate de regresiones de eval es estricto en señales deterministas (cualquier desvio en seleccion de tool, argumentos, grounding, confirmacion u outcome bloquea la release) y usa umbrales de politica versionada para costo y latencia; evita gates fragiles sobre comportamiento LLM no determinista.
- [RESUELTO Q3 - opcion A]: el presupuesto agotado aplica bloqueo duro recuperable: la ejecucion se detiene o rechaza con estado tipado y mensaje claro, y el usuario retoma al reiniciarse la ventana de politica o con una accion explicita; 0 degradacion de calidad del modelo.
- [RESUELTO Q4 - opcion B]: los evals son hibridos en fidelidad de modelo: el gate (harness y CI) usa adapter determinista simulado (reproducible, 0 costo) y los evals con el proveedor real corren en flujo separado, programado y con presupuesto de eval acotado por politica; el ADR define el proveedor para el flujo real.
- [RESUELTO Q5 - opcion B]: el dataset golden inicial tiene al menos 3 casos por familia (21 casos total) con revision de producto; es versionado y ampliable en incrementos posteriores, y las familias criticas (injection, rechazo seguro, cambios ambiguos) pueden pedir mas casos que el minimo.
- [RESUELTO Q6 - opcion C]: la activacion de releases es hibrida: automatica para cambios de codigo/topologia/schemas con gate verde, y con aprobacion explicita de un operador (reporte de eval como evidencia) para cambios de prompts o modelos.
- 0 cambios a matching, scoring, dedupe o ingesta; el incremento agrega dataset, evals, releases, presupuestos, dashboard y ADR sobre los registros existentes.
