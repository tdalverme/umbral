# Feature Specification: Cierre de alineacion con SPEC (feedback estructurado, conceptos economicos, flujo de validacion)

**Feature Directory**: `specs/019-spec-alignment`

**Created**: 2026-08-20

**Status**: Draft

**Input**: SPEC.md (contrato de producto global) contrastada contra el estado del
repositorio (specs 001-018, ADRs, `CONTEXT.md`). El grilling resolvio los
conflictos en ADR 0002 (`session-scoping`) y ADR 0003 (`structured-concept-feedback`),
y acoto el trabajo de cierre a tres piezas: feedback estructurado por concepto,
conceptos economicos derivables hoy y un test golden-path que demuestre los dos
flujos de validacion de la SPEC.

## Operational Definitions

- **Concepto**: caracteristica compartida de una vivienda o su entorno que Umbral observa y evalua con una semantica versionada (`CONTEXT.md`).
- **Feedback estructurado por concepto**: interpretacion versionada del lenguaje de feedback en entradas `concept_key + polarity + strength + confidence` que el agente produce y un servicio controlado consume.
- **Senal de aprendizaje**: conteo determinista de feedback concepto-razonado consistente dentro de la ventana del learning policy (`feedback/signals.py`).
- **Flujo de validacion**: cadena completa listing ingested -> normalized -> enriched -> candidate retrieval -> personalized ranking -> match explanation; y user feedback -> structured interpretation -> preference update -> reranking.

## Relationship to Existing Features

Extiende `007-feedback-learning` (feedback inmutable + proposals HITL) con el
puente de interpretacion por concepto, y `015-catalog-concept-expansion`/`018`
con dos conceptos economicos de regla. Cierra el vacio de evidencia de la suite
con un test de integracion "golden path". No cambia scoring policy, notification
policy, ingesta Bronze/Silver ni identity. La capa de observacion->derivado
(SPEC §13), imagenes (SPEC §4.3/§7.3) y session overrides reales quedan en
backlog (ADR 0002, notas NA-02/NA-04/NA-10 de SPEC.md).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Feedback libre que alimenta el aprendizaje por concepto (Priority: P1)

Como persona que comenta un listado con sus palabras, quiero que "me gusta pero
la cocina es chica e integrada" se traduzca en senales por concepto
(`cocina` tamaño negativo/fuerte, `tipo_cocina` negativo/medio) y alimente
propuestas de aprendizaje confirmables, para que mi feedback deje de perderse
en texto suelto.

**Why this priority**: es el punto 9 del Definition of Done de la SPEC (§39) y
el caso §28.2; hoy el texto libre no produce ninguna senal.

**Independent Test**: registrar feedback `like` con `concept_feedback`
(`tipo_cocina` negative/strong) produce una `LearningProposal` pendiente cuando
se alcanza el umbral del learning policy; ningun cambio se aplica sin
confirmacion.

**Acceptance Scenarios**:

1. **Given** un listado visible en el run vigente, **When** el agente registra feedback con `concept_feedback[]`, **Then** se persisten `FeedbackEventReason` con concepto, polaridad, strength, confidence y el fragmento de evidencia textual en el evento (0 PII en analytics).
2. **Given** dos `like` razonados con el mismo concepto y polaridad dentro de la ventana, **When** se evaluan las senales, **Then** el conteo `min_signals` del learning policy versionado produce una `LearningProposal` pendiente con `evidence_event_ids`.
3. **Given** una proposal pendiente, **When** el usuario confirma, **Then** se crea el `PreferenceFact` (source feedback), se versiona el radar y se agenda recomputo; el run previo queda congelado.
4. **Given** un concepto fuera del catalogo activo ("el palier es raro"), **When** se interpreta el feedback, **Then** se conserva como `free_feedback` textual sin concepto inventado y el copiloto sugiere conceptos cercanos evaluables.
5. **Given** una interpretacion con concepto semantico (p.ej. `moderno`), **When** se registra, **Then** la polaridad se conserva y la proposal resultante nunca modifica fuerza hard del radar.

### User Story 2 - Conceptos economicos de regla (Priority: P2)

Como persona que compara oportunidades, quiero que "m2 bien de precio" y "bajo
de precio" impacten la busqueda, para que el factor economico deje de ser solo
el presupuesto duro.

**Why this priority**: son los unicos conceptos del bloque economico de SPEC §37
derivables sin infraestructura nueva (sin batch ni recompute periodico).

**Independent Test**: un listado con `price` y `surface_m2` produce la
observacion `precio_m2` por regla determinista con evidencia; un listado con
`listing_changes` de precio produce `variacion_precio`; listados sin dato
producen `unknown`.

**Acceptance Scenarios**:

1. **Given** un listado Silver con `price_value`, `currency` y `surface_m2`, **When** se ejecuta la extraccion, **Then** `precio_m2` se observa por regla con el cociente documentado (misma moneda, sin conversion no versionada) y evidencia de los campos usados.
2. **Given** un listado con `listing_changes` tipo `price`, **When** se ejecuta la extraccion, **Then** `variacion_precio` se observa como delta numerico con la convencion de signo declarada (baja/igual/subida) y evidencia del cambio.
3. **Given** un listado sin `surface_m2`, **When** se extrae `precio_m2`, **Then** la observacion queda `unknown` (nunca un promedio inventado).
4. **Given** el catalogo con los conceptos nuevos, **When** el copiloto escucha "que no se me vaya de precio", **Then** propone bindings soft sobre `variacion_precio` via vocabulario canonico sin cambios de codigo del agente.

### User Story 3 - Flujo de validacion golden-path (Priority: P1)

Como equipo, quiero un unico test de integracion que ejecute los dos flujos
completos sobre Postgres real, para demostrar el Definition of Done de la SPEC
(§39) y cerrar el vacio de la suite (hoy solo hay tests por etapa + lineage).

**Why this priority**: es la validacion minima exigida por el producto; no
existe ningun e2e de negocio (el unico test e2e es de telemetria).

**Independent Test**: el test corre en CI (testcontainers Postgres) con fakes
deterministas (geocoder, extractor) y verifica: flujo A ingest -> normalize ->
enrich -> candidates -> rank -> explain; flujo B feedback con
`concept_feedback` -> proposal -> confirm -> nuevo run con el hecho aplicado.

**Acceptance Scenarios**:

1. **Given** un batch de import sintetico, **When** corre el flujo A, **Then** el listado llega a Silver, se extraen observaciones (regla + urban/rule), el run publica items ordenados y la explicacion del top 1 cita evidencia interna.
2. **Given** el flujo A completo, **When** se registra feedback con concepto y se confirma la proposal, **Then** se versiona el perfil, el nuevo run refleja el hecho (cambio de orden o contribucion) y la explicacion nueva lo declara.
3. **Given** el flujo B, **When** se repite, **Then** la idempotencia del feedback (mismo idempotency_key) no crea senales duplicadas.

## Edge Cases

- Feedback con concepto no catalogo o no computable -> texto preservado, sin inventar concepto.
- `precio_m2` con moneda mixta o sin superficie -> unknown con motivo.
- `variacion_precio` sin cambios de precio previos -> unknown (no "sin cambio" implicito).
- El usuario registra `dislike` con concepto que ya tiene una hipotesis pendiente -> supersesion o dedupe segun estado de `feedback_events` (append-only).
- Concepto semanticos: el feedback jamas genera fuerza hard (learning nunca crea hard, spec 018).
- Contratos del tool `record_feedback` actualizados: los evals y la abuse suite deben seguir pasando con el payload nuevo.
- Registry de eventos: `feedback.recorded.v1` debe admitir el payload extendido sin romper la validacion estricta existente.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El tool del agente `record_feedback` MUST aceptar `concept_feedback[]` con `{concept_key, polarity, strength, confidence}` ademas de `reason_keys`, via contrato versionado (nueva version o extension conforme a convencion).
- **FR-002**: La interpretacion del feedback libre en `concept_feedback[]` MUST usar un schema versionado de salida estructurada (patron `preference-interpret`); el LLM MUST NOT elegir conceptos ni pesos finales.
- **FR-003**: Los `FeedbackEventReason` MUST persistir `strength` (low|medium|strong) y `confidence` ([0,1]) ademas de concepto y polaridad (migracion 0019).
- **FR-004**: El motor de senales MUST conservar el policy versionado intacto: el conteo usa polaridad dentro de la ventana; strength/confidence se conservan como evidencia y MUST NOT modular el counting ni los thresholds en V1.
- **FR-005**: El feedback estructurado MUST producir `LearningProposal` solo por el camino existente (HITL, 0 auto-apply); jamas genera `soft_to_hard`.
- **FR-006**: Los conceptos fuera del catalogo activo MUST preservarse como `free_feedback` textual con sugerencia de conceptos cercanos; MUST NOT crearse conceptos por chat.
- **FR-007**: El catalogo MUST agregar los conceptos `precio_m2` y `variacion_precio` (matcher `numeric_range`) con reglas deterministas en `criteria/rules.py`, goldens de extraccion y entradas de vocabulario canonico.
- **FR-008**: `precio_m2` MUST usar `price_value` + `surface_m2` en la misma moneda del listado (sin conversion no versionada); `unknown` si faltan campos.
- **FR-009**: `variacion_precio` MUST derivar de `listing_changes` tipo `price` con convencion de signo declarada; `unknown` sin cambios previos.
- **FR-010**: El test golden-path MUST ejecutar ambos flujos completos sobre Postgres real con adapters deterministicos y MUST formar parte del harness `scripts/check.ps1` (nuevo `check-019.ps1` o inclusion en bundle existente).

### Backlog (fuera de alcance, documentado)

- Imagenes (SPEC NA-04), session overrides reales (NA-02), `days_on_market` y
  `price_vs_comparables` (NA-08), capa observacion->derivado (NA-10), evaluacion
  por pares de features (NA-11), emision del trigger `price_drop` (NA-09).

## Definition of Done

- ADR 0002 y 0003 aceptados y referenciados desde SPEC.md (Appendix A). ✔ (ya escritos)
- El feedback libre con concepto llega a proposal HITL con evidencia (US1).
- `precio_m2` y `variacion_precio` observables por regla con goldens y vocabulario (US2).
- Test golden-path de los dos flujos corre verde en harness local (US3).
- Sin cambios en scoring/notification policy; 0 regresiones en los checks
  existentes (ruff, mypy, import-linter, pytest, migrations).