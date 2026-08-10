# Feature Specification: Calidad del matching

**Feature Branch**: `008-matching-quality`

**Created**: 2026-08-09

**Status**: Draft

**Input**: User description: "Arranquemos con la especificacion de la epica H3.4 - Calidad del matching del backlog, con alcance exacto UM-H3-032 a UM-H3-035."

## Clarifications

### Session 2026-08-09

- Q: ¿Que cambio de ranking debe bloquear el gate de regresiones? → A: Gate
  estricto: cualquier cambio de orden relativo entre dos versiones sobre el
  mismo dataset bloquea, y los hard filters tienen 0 tolerancia; las
  diferencias de score que no alteran el orden son reporte informativo y no
  bloquean.
- Q: ¿Como se registra y verifica que un cambio de scoring esta "explicado"
  para que el gate lo deje pasar? → A: La release de la nueva version
  (policy, parser, prompt o concepto) incluye la explicacion y el responsable;
  el harness verifica que exista y la contrasta con el diff real: los casos
  afectados declarados deben coincidir con los detectados. 0 explicaciones se
  escriben fuera de la release versionada.
- Q: ¿Que umbral cuantitativo debe cumplir el reporte agregado de fidelidad de
  explicaciones para no fallar? → A: Gate estricto como el de regresiones: el
  100% de los hechos afirmados con evidencia, 0 contradicciones y 0
  afirmaciones sin soporte en todos los casos; el reporte falla ante la
  primera violacion.
- Q: ¿Que relacion tiene este incremento con el dataset golden y las
  regresiones cuando aun no hay usuarios reales? → A: El dataset golden se
  construye sobre el dataset controlado de beta y los casos curados de H2 y H3
  (perfiles, listings, hard filter violations, unknowns, preferencias
  subjetivas y orden esperado revisado por producto). Las regresiones lo
  protegen desde hoy: toda version de scoring o de extraccion se compara
  contra ese orden esperado y bloquea cambios no explicados, antes de exponer
  el matching al chat (H4) o a alertas (H5).
- Q: ¿Que alcance tiene la evaluacion de fidelidad de explicaciones
  (UM-H3-034) si las explicaciones v1 son deterministas sin LLM? → A: La
  fidelidad se mide sobre el desglose persistido de cada recomendacion:
  cobertura de evidencia (todo hecho afirmado tiene su evidence ref),
  contradicciones (0 hechos que contradicen el desglose), afirmaciones no
  soportadas (0 hechos sin evidencia) y copy de incertidumbre (desconocidos y
  baja confianza declarados). El copy generativo opcional futuro (H4) debe
  pasar la misma evaluacion.
- Q: ¿Que produce la revision de fairness (UM-H3-035, P1) como entregable? →
  A: Un documento versionado que revisa features, conceptos, copy y lenguaje
  geografico, identifica features prohibidas y las documenta en el registry
  (H3.1) como no computables, sin construir nueva infraestructura.
- Q: ¿Como se integra el dataset golden en el harness de checks? → A: El
  harness de H3.4 se registra en `check.ps1` como los anteriores: construye el
  dataset golden, ejecuta regresiones de scoring, evalua fidelidad de
  explicaciones y reporta el estado de la revision de fairness; el gate de
  regresiones bloquea cuando un cambio no esta explicado.

## Operational Definitions

- **Dataset golden de recomendaciones**: conjunto versionado y curado de casos
  (perfil de busqueda + listings + contexto de fuente/datos) con el orden de
  recomendacion esperado, revisado por producto, que cubre hard filter
  violations, unknowns, preferencias subjetivas, precios/expensas y limites del
  scoring. Es la referencia inmutable para regresiones.
- **Regresion de scoring**: comparacion automatica entre dos versiones de
  scoring/extraccion sobre el dataset golden: orden relativo, scores por item y
  gate/confianza por caso; detecta cambios no explicados y bloquea el gate.
  El gate bloquea ante cualquier cambio de orden relativo o de hard filters;
  las diferencias de score que no alteran el orden son reporte informativo.
- **Cambio explicado**: diferencia entre versiones justificada por una
  modificacion intencional (policy, parser, prompt, concepto o datos) y
  documentada en la release de la nueva version con responsable; el harness
  verifica que la explicacion exista y que los casos afectados declarados
  coincidan con los detectados. Un cambio no explicado es una regresion.
- **Fidelidad de explicacion**: grado en que una explicacion solo afirma hechos
  soportados por evidencia persistida, sin contradecir el desglose y
  declarando desconocidos/confianza baja; se mide con metricas automaticas.
- **Features prohibidas**: atributos o proxies que el producto no permite usar
  para matching/explicaciones por riesgo de sesgo o discriminacion (por
  ejemplo, inferencias sensibles o lenguaje normativo sobre zonas),
  documentadas como no computables.
- **Revision de fairness**: evaluacion de features, conceptos, copy y lenguaje
  geografico contra la politica de no discriminacion; produce el registro de
  features prohibidas y recomendaciones sin construir infraestructura.

## Review and Measurement Protocol

- La puerta de salida de H3.4 es que el matching quede protegido antes del
  chat (H4) y las alertas (H5): el dataset golden se construye y versiona, las
  regresiones corren sobre el, las explicaciones pasan la evaluacion de
  fidelidad y la revision de fairness deja documentadas las features
  prohibidas.
- El dataset golden se verifica confirmando que cubre los casos acordados con
  producto (hard filter violations, unknowns, preferencias subjetivas, limites
  de precio/expensas y orden esperado), que es consultable y versionado y que
  su orden esperado fue revisado por producto con evidencia.
- Las regresiones se verifican comparando la misma entrada contra dos
  versiones de scoring: el 100% de los casos se evalua, los cambios no
  explicados se detectan y bloquean, y los cambios explicados se documentan y
  pasan.
- La fidelidad de explicaciones se verifica sobre el desglose persistido: el
  100% de los hechos afirmados tiene evidencia, 0 contradicciones con el
  desglose, 0 afirmaciones sin soporte y el 100% de los casos con
  desconocidos/confianza baja lo declara.
- La revision de fairness se verifica con el registro de features prohibidas
  documentadas y consultable, sin construir nueva infraestructura y con el
  copy/features revisados contra la politica.
- La instrumentacion y los contratos de H3.4 se limitan al harness interno: 0
  superficies nuevas de producto, 0 endpoints de usuario y 0 eventos de
  producto nuevos; el harness emite reportes auditables sin PII.
- Los checks se integran en el harness local (`scripts/check.ps1`) y se
  ejecutan en CI de acuerdo con la convencion de los incrementos previos.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Proteger el matching con un dataset golden (Priority: P0)

Como equipo de producto y desarrollo, quiero un dataset golden versionado con
el orden esperado revisado por producto, para que toda decision de ranking
tenga una referencia objetiva y auditable.

**Why this priority**: Es la base de H3.4: sin una referencia de verdad no se
puede detectar una regresion antes de exponer el matching al chat y a las
alertas.

**Independent Test**: El conjunto de prueba construye el dataset golden y
verifica cobertura, versionado y revision por producto.

**Acceptance Scenarios**:

1. **Given** el dataset controlado de beta y los casos curados de H2/H3,
   **When** se construye el dataset golden, **Then** cubre hard filter
   violations, unknowns, preferencias subjetivas, precios/expensas y el orden
   esperado por caso, revisado por producto con evidencia.
2. **Given** un caso del dataset, **When** se consulta, **Then** es trazable a
   sus listings, perfiles y contexto de fuente/datos y tiene el orden esperado
   documentado.
3. **Given** una version nueva del dataset, **When** se genera, **Then** queda
   versionada e inmutable y la version anterior sigue consultable.
4. **Given** el dataset, **When** corre el harness, **Then** es la referencia
   de las regresiones y de la evaluacion de fidelidad sin depender de datos
   efimeros.

---

### User Story 2 - Automatizar regresiones de scoring (Priority: P0)

Como equipo, quiero que cada version de scoring/extraccion se compare contra el
dataset golden y bloquee cambios no explicados, para que ninguna regresion
llegue al producto sin ser detectada.

**Why this priority**: Es el guardrail de confianza del hito: el matching debe
ser deterministico y estable, y un cambio accidental debe frenarse antes de
afectar recomendaciones.

**Independent Test**: El conjunto de prueba corre el mismo dataset contra dos
versiones, induce un cambio no explicado y verifica que se detecta y bloquea.

**Acceptance Scenarios**:

1. **Given** el dataset golden y una version de scoring, **When** se ejecuta la
   regresion contra la version anterior, **Then** se compara orden relativo,
   scores y gate/confianza por el 100% de los casos.
2. **Given** un cambio no explicado (por ejemplo, un parser que altera un
   feature sin version nueva), **When** corre la regresion, **Then** se detecta
   y el gate bloquea la publicacion con el diff y los casos afectados.
3. **Given** un cambio explicado (nueva version de policy, parser, prompt,
   concepto o datos documentada), **When** corre la regresion, **Then** pasa si
   el impacto esta documentado y acotado.
4. **Given** una regresion en hard filters, **When** se detecta, **Then** es
   bloqueante siempre: 0 filtros duros se degradan sin revision.
5. **Given** el harness, **When** se integra en checks, **Then** se registra en
   `check.ps1` y corre en CI de acuerdo con la convencion del proyecto.

---

### User Story 3 - Evaluar la fidelidad de las explicaciones (Priority: P0)

Como equipo, quiero medir automaticamente si cada explicacion solo afirma lo
que la evidencia soporta, declara incertidumbre y no contradice el desglose,
para que el usuario nunca reciba razones inventadas.

**Why this priority**: Protege el principio de matching auditable: las
explicaciones son parte de la confianza y deben ser verificables como el
scoring mismo.

**Independent Test**: El conjunto de prueba alimenta explicaciones con hechos
soportados, no soportados y contradictorios y verifica que la metrica los
distingue y que los desconocidos se declaran.

**Acceptance Scenarios**:

1. **Given** una recomendacion persistida con su desglose, **When** se evalua su
   explicacion, **Then** cada hecho afirmado tiene su evidence ref y 0
   afirmaciones sin soporte se consideran validas.
2. **Given** una explicacion con un hecho que contradice el desglose, **When**
   se evalua, **Then** se detecta como contradiccion y se reporta.
3. **Given** un caso con datos faltantes o confianza baja, **When** se evalua,
   **Then** se verifica que la incertidumbre esta declarada en la explicacion.
4. **Given** el evaluador, **When** corre el harness, **Then** produce un reporte
   agregado de fidelidad sobre el dataset golden y falla ante la primera
   violacion (100% de hechos con evidencia, 0 contradicciones, 0 sin soporte).
5. **Given** un copy generativo futuro (H4), **When** se introduce, **Then**
   debe pasar la misma evaluacion de fidelidad antes de publicarse.

---

### User Story 4 - Revisar fairness y lenguaje geografico (Priority: P1)

Como equipo, quiero revisar features, conceptos, copy y lenguaje geografico
para evitar inferencias sensibles, proxies discriminatorios y afirmaciones
normativas sobre zonas, y documentar las features prohibidas.

**Why this priority**: Es P1 del backlog: no bloquea el camino critico, pero
deja asentada la politica de no discriminacion antes de escalar el matching.

**Independent Test**: El conjunto de prueba revisa el registry, features y copy
y verifica que las features prohibidas quedan documentadas como no computables.

**Acceptance Scenarios**:

1. **Given** el registry de conceptos y las features de H3.1/H3.2, **When** se
   revisa, **Then** se identifican y documentan las features prohibidas como no
   computables.
2. **Given** el copy y el lenguaje geografico actual, **When** se revisa,
   **Then** 0 afirmaciones normativas sobre zonas o inferencias sensibles se
   emiten.
3. **Given** un proxy discriminatorio propuesto, **When** se evalúa, **Then**
   se marca como prohibido y se documenta con su justificacion.
4. **Given** la revision, **When** se cierra, **Then** deja un documento
   versionado consultable sin construir infraestructura nueva.

### Edge Cases

- Un caso del dataset golden con unknowns (sin dato de superficie, ambientes o
  expensas) debe tener el orden esperado definido bajo la politica de
  desconocido de H3.2, no quedar fuera del dataset.
- Un cambio de parser que altera features de forma masiva y no intencional se
  detecta como regresion y bloquea; no se "arregla" silenciosamente.
- Una regresion en un solo caso afecta el gate: el reporte debe listar los
  casos exactos y el diff para accionar.
- Un cambio explicado documentado no bloquea, pero queda registrado para
  auditoria (version de policy/parser/prompt/concepto y responsables).
- Las explicaciones de listings legacy (sin desglose de H2.3) no se evalúan
  como fidelidad completa: se declaran sin desglose y 0 razones se fabrican.
- El evaluador de fidelidad distingue hecho soportado, hecho sin soporte y
  contradiccion; los tres estados quedan reportados por caso.
- Las features prohibidas se documentan en el registry como no computables y 0
  endpoints o superficies de producto nuevas se crean en este incremento.
- El harness de H3.4 no emite eventos de producto ni PII: solo reportes
  auditables internos.
- El dataset golden no depende de datos efimeros: es versionado e inmutable,
  y la version anterior queda consultable tras cada actualizacion.

## Requirements *(mandatory)*

### Functional Requirements

#### Dataset golden

- **FR-001**: El sistema MUST mantener un dataset golden versionado e inmutable
  de casos de recomendacion (perfil + listings + contexto de fuente/datos) con
  el orden esperado por caso, revisado por producto y trazable a sus datos.
- **FR-002**: El dataset golden MUST cubrir hard filter violations, unknowns,
  preferencias subjetivas y limites de precio/expensas, con el orden esperado
  definido bajo la politica de desconocido de H3.2.

#### Regresiones de scoring

- **FR-003**: El sistema MUST comparar automaticamente dos versiones de
  scoring/extraccion sobre el dataset golden: orden relativo, scores por item y
  gate/confianza por el 100% de los casos.
- **FR-004**: El gate de regresion MUST bloquear cambios no explicados con el
  diff y los casos afectados; 0 regresiones en hard filters se toleran sin
  revision. El gate MUST bloquear ante cualquier cambio de orden relativo entre
  dos versiones sobre el mismo dataset y ante cualquier cambio de hard filters;
  las diferencias de score que no alteran el orden MUST registrarse como
  reporte informativo y MUST NO bloquear.
- **FR-005**: Un cambio explicado y documentado (version de policy, parser,
  prompt, concepto o datos) MUST poder pasar la regresion y quedar registrado
  para auditoria. La explicacion MUST vivir en la release de la nueva version
  con su responsable, y el harness MUST verificar que los casos afectados
  declarados coincidan con los detectados; 0 explicaciones MUST escribirse
  fuera de la release versionada.

#### Fidelidad de explicaciones

- **FR-006**: El sistema MUST evaluar automaticamente cada explicacion sobre el
  desglose persistido: cobertura de evidencia (todo hecho con su evidence ref),
  0 contradicciones con el desglose, 0 afirmaciones sin soporte y declaracion
  de desconocidos/confianza baja.
- **FR-007**: El evaluador de fidelidad MUST fallar con umbral estricto: 100%
  de los hechos afirmados con evidencia, 0 contradicciones y 0 afirmaciones
  sin soporte en todos los casos del dataset golden, y MUST declarar listings
  legacy sin desglose sin fabricar razones.

#### Fairness y lenguaje geografico (P1)

- **FR-008**: La revision de fairness MUST identificar y documentar features
  prohibidas y proxies discriminatorios como no computables en el registry
  (H3.1), y revisar el copy y lenguaje geografico contra la politica de no
  discriminacion.
- **FR-009**: La revision MUST producir un documento versionado y consultable
  sin construir infraestructura nueva.

#### Transversal

- **FR-010**: El incremento MUST integrar el harness de H3.4 en `check.ps1` y
  ejecutarse en CI de acuerdo con la convencion de los incrementos previos.
- **FR-011**: El harness MUST emitir reportes auditables sin PII y 0 eventos de
  producto nuevos; 0 superficies de usuario y 0 endpoints de producto se crean
  en este incremento.
- **FR-012**: La evaluacion de fidelidad MUST aplicarse tambien a cualquier copy
  generativo futuro (H4) antes de su publicacion.

### Key Entities

- **Golden Dataset**: conjunto versionado de casos de recomendacion con orden
  esperado revisado por producto, referencia inmutable de regresiones y
  fidelidad.
- **Regression Run**: ejecucion de comparacion de dos versiones de
  scoring/extraccion sobre el dataset golden con su resultado y diff.
- **Explanation Fidelity Report**: metrica por caso y agregada de cobertura de
  evidencia, contradicciones, afirmaciones sin soporte y declaracion de
  incertidumbre.
- **Forbidden Feature Registry**: registro de features y proxies prohibidos
  documentados como no computables.
- **Fairness Review Document**: documento versionado de la revision de
  features, conceptos, copy y lenguaje geografico.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Dataset golden | UM-H3-032 |
| User Story 2 - Regresiones de scoring | UM-H3-033 |
| User Story 3 - Fidelidad de explicaciones | UM-H3-034 |
| User Story 4 - Fairness y lenguaje | UM-H3-035 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H3-032 | FR-001, FR-002, FR-010 | US1.1-US1.4, SC-001 |
| UM-H3-033 | FR-003, FR-004, FR-005, FR-010 | US2.1-US2.5, SC-002, SC-003 |
| UM-H3-034 | FR-006, FR-007, FR-012 | US3.1-US3.5, SC-004 |
| UM-H3-035 | FR-008, FR-009 | US4.1-US4.4, SC-005 |
| Transversal (todos) | FR-010, FR-011 | SC-006 |

## Constitution Alignment *(mandatory)*

- **Auditable deterministic matching**: el dataset golden, las regresiones y la
  fidelidad de explicaciones refuerzan que el ranking final y sus razones son
  versionados, deterministicos y verificables; el evaluador de fidelidad
  aplica a cualquier copy generativo futuro sin ceder la verdad al LLM.
  Sustenta el principio II.
- **Data lineage, observability and trust**: el dataset golden es versionado e
  inmutable y cada caso traza a sus listings, perfiles y contexto; los
  reportes son auditables sin PII. Sustenta el principio V.
- **Versioned prompts, models and schemas**: las regresiones comparan versiones
  y los cambios no explicados bloquean; las features prohibidas se documentan
  como no computables en el registry versionado. Sustenta el principio II y V.
- **Verification approach**: el incremento ES verificacion: dataset golden
  revisado por producto, regresiones automatizadas, evaluacion de fidelidad
  automatica y revision de fairness documentada, todos integrados en el
  harness y en CI.
- **Dependency direction**: el harness consume scoring, extraccion,
  explicaciones y registry como dependencias; no accede libremente a la base ni
  agrega acceso del agente.
- **Minimal change**: el incremento se limita a UM-H3-032 a UM-H3-035 y excluye
  features, UI, endpoints y eventos de producto nuevos; el chat (H4) y las
  alertas (H5) quedan fuera.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de los casos del dataset golden tiene orden esperado
  revisado por producto, es trazable y consultable; 0 versiones se mutan y la
  anterior queda consultable.
- **SC-002**: El 100% de los casos del dataset golden se compara en cada
  regresion; el 100% de los cambios no explicados se detecta y bloquea con el
  diff y los casos afectados, y el 100% de los cambios documentados pasa y
  queda registrado.
- **SC-003**: 0 regresiones de hard filters se publican sin revision; el gate
  de regresiones bloquea siempre ante cambios de orden relativo o de hard
  filters.
- **SC-004**: El 100% de los hechos afirmados en las explicaciones evaluadas
  tiene evidencia, 0 contradicciones y 0 afirmaciones sin soporte; el 100% de
  los casos con desconocidos/confianza baja lo declara, y el reporte falla con
  umbral estricto ante la primera violacion.
- **SC-005** (P1): El 100% de las features prohibidas y proxies
  discriminatorios identificados queda documentado como no computable en el
  registry; 0 afirmaciones normativas sobre zonas se emiten en el copy.
- **SC-006**: El harness de H3.4 se registra en `check.ps1`, corre en CI y emite
  reportes auditables sin PII; 0 superficies de usuario, 0 endpoints de
  producto y 0 eventos de producto nuevos en el incremento.

## Assumptions

- El alcance incluye exactamente UM-H3-032 a UM-H3-035 (Epica H3.4 - Calidad
  del matching). El chat (H4) y las alertas (H5) quedan fuera y se especifican
  en sus propios incrementos.
- Depende de H3.1 (concept registry, preference facts, compilacion), H3.2
  (scoring policy versionada, runs atomicos, explicaciones desde evidencia) y
  H3.3 (feedback/learning) como maquinaria existente: este incremento la
  protege y NO la reimplementa.
- El dataset golden se construye sobre el dataset controlado de beta y los
  casos curados de H2/H3, con el orden esperado revisado por producto. Los
  valores exactos (cantidad de casos, umbrales) se definen en el plan y los
  contratos sin cambiar el alcance.
- Una regresion es un cambio no explicado entre versiones de
  scoring/extraccion: se detecta comparando orden, scores y gate/confianza. Un
  cambio explicado es una nueva version de policy, parser, prompt, concepto o
  datos documentada en la release con responsable, y el harness verifica que
  los casos afectados declarados coincidan con los detectados.
- Las regresiones de hard filters y cualquier cambio de orden relativo entre
  versiones son siempre bloqueantes; las diferencias de score que no alteran el
  orden son reporte informativo y no bloquean.
- La evaluacion de fidelidad opera sobre el desglose persistido de H3.2. Los
  listings legacy sin desglose se declaran sin desglose y 0 razones se
  fabrican. Cualquier copy generativo futuro (H4) debe pasar la misma
  evaluacion.
- La revision de fairness (UM-H3-035, P1) es un entregable documental
  versionado: features prohibidas y proxies documentados como no computables en
  el registry, y revision de copy y lenguaje geografico; no construye
  infraestructura nueva.
- El harness de H3.4 se integra en `check.ps1` y corre en CI de acuerdo con la
  convencion de los incrementos previos, emitiendo reportes auditables sin PII.
- Este incremento no expone superficies de usuario, endpoints de producto ni
  eventos de producto nuevos: es verificacion interna y documental.
- El idioma de los casos golden, el copy y los reportes es espanol (CABA),
  sobre el dataset controlado.
