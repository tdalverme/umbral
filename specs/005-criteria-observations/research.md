# Research: Criteria and Observations

**Feature**: `005-criteria-observations` | **Date**: 2026-08-06

Decisions recorded for the H3.1 increment (UM-H3-001 a UM-H3-011). Format per
item: Decision / Rationale / Alternatives considered.

## R-01 — Concept registry como agregado versionado con seed machine-checkable

**Decision**: el concept registry v1 es un agregado de dominio con tabla
`concepts` (estado actual) + `concept_versions` (inmutables), donde cada
cambio (registro o edicion) crea una version nueva sin mutar la anterior
(FR-001). La curaduria inicial entra como seed versionado cargado desde
`contracts/criteria/v1/concepts-seed-v1.json` (clarificacion 2026-08-06: sin
contratos HTTP; el operador no tiene superficie en este incremento, FR-024).
La validacion de matcher types y parametros permitidos vive en un registry
puro cargado desde `contracts/criteria/v1/matcher-types-v1.json` (FR-002); los
alias resuelven a un unico concepto canonico y las colisiones se reportan como
advertencias (FR-003).

**Rationale**: versionar el registry como agregado con historial inmutable es
lo que exigen FR-001/FR-003 y lo que la recomputacion selectiva necesita
(UM-H3-011): una version de concepto invalida solo las observaciones de ese
concepto. El seed versionado evita la superficie de curaduria (H6) y hace la
taxonomia reproducible y testeable contra casos golden.

**Alternatives**: registry como un unico JSON en el contrato sin tabla
(rechazado: los cambios no quedarian auditados ni versionados); API de
curaduria con rol operador (rechazado por la clarificacion: la consola
operativa es H6).

## R-02 — Preference facts append-only con estado y supersesion

**Decision**: `preference_facts` es append-only: cada fila persiste valor,
peso, polaridad, confianza, fuente, estado de validez y alcance por busqueda
(FR-004). Un cambio de decision inserta una fila nueva y supersede la anterior
(`state = superseded`, `superseded_by` apuntando a la nueva); nunca se muta la
anterior. La vigente es la fila `active` mas reciente por
`(profile_id, concept_key)` (FR-004/FR-005, deny-by-default por ownership del
perfil).

**Rationale**: inmutabilidad + supersesion da trazabilidad de la evolucion de
preferencias sin mutaciones destructivas; el patron es el mismo de
observaciones y versiones de perfil ya aceptado en el repo.

**Alternatives**: una fila mutable por (profile, concept) (rechazado: viola la
trazabilidad de FR-004); fact deltas solo en memoria (rechazado: la fuente de
verdad debe ser persistente).

## R-03 — Criterios ejecutables y compilacion versionada

**Decision**: la compilacion es una funcion pura `compile_criteria(inputs) ->
Compilation` que toma el perfil (payload de `search_profile_versions`), los
preference facts vigentes y las ediciones estructuradas (seed de ediciones +
confirmaciones), y produce un conjunto ordenado y versionado de criterios con
advertencias (FR-006/FR-007/FR-008). Cada criterio ejecutable referencia
concepto, matcher type y parametros validados contra matcher-types-v1, y la
version del fact o edicion de origen. La memoria semantica del perfil nunca se
compila como criterio sin una edicion explicita validada; la conversion de una
preferencia blanda en hard filter exige una confirmacion registrada en la
compilacion y falla sin ella (FR-007). Las compilaciones se persisten en
`profile_criteria_compilations` (una o mas por profile version; la vigente es
la de mayor version).

**Rationale**: separar memoria semantica de instrucciones evaluables es el
punto que evita que el chat (H4) mute el radar silenciosamente; una funcion
pura con casos golden es lo mas testeable y el input del scoring H3.2.

**Alternatives**: guardar criterios como JSON dentro del profile version
(rechazado: mezcla memoria semantica con instrucciones y no da advertencias ni
confirmaciones auditables); compilacion solo como resultado de LLM (rechazado:
la constitucion prohibe que el LLM decida criterios de ranking).

## R-04 — Observaciones: identidad, estados y supersesion

**Decision**: `listing_observations` es append-only con `state` en
`active | invalidated | superseded | failed` y un indice unico parcial
`(listing_id, concept_key, source) WHERE state = 'active'` que garantiza a
nivel DB a lo sumo una observacion vigente por par (clarificacion 2026-08-06;
FR-009, SC-012). Cada observacion persiste concepto, valor (JSONB), score,
confianza, evidencia (fragmento + campo de origen), fuente (`rule` | `model`),
version de extraccion (FK a `extraction_versions`) y timestamp (FR-009).
Recomputar = insertar nuevas `active` + superseder las `invalidated` previas
en una sola transaccion.

**Rationale**: el indice parcial unico convierte SC-012 en invariante de DB, no
solo de tests; los estados distinguen "reemplazada" de "esperando recomputo"
(FR-015/FR-017) y de "fallo acotado" (FR-012).

**Alternatives**: una fila mutable por par (rechazado: pierde historial de
version); multiples vigentes concurrentes (rechazado por la clarificacion:
consumo ambiguo).

## R-05 — Extraccion objetiva por reglas con evidencia de fragmento

**Decision**: las reglas son funciones puras registradas por concepto
(`rules.py`) sobre campos permitidos del listing normalizado
(`description_text`, `location_text`, `amenities`, atributos estructurados),
versionadas en `extraction_versions` (kind=`rule`, key=concepto) y con casos
golden obligatorios (FR-010). Cada observacion de regla conserva evidencia de
fragmento: el substring matcheado y el campo de origen
(`{fragment, span, matched_on}`); sin fragmento la observacion declara
"sin evidencia" explicito. Seed v1: `balcon`, `ambientes`, `piso`,
`tipo_cocina`.

**Rationale**: determinismo puro con doble ejecucion identica (SC-004) y
evidencia textual verificable; el fragmento es la base de las explicaciones
futuras (H3.2).

**Alternatives**: reglas como prompts/LLM (rechazado: viola la exigencia de
reglas deterministicas de UM-H3-006); regex inline sin version ni golden
(rechazado: no testeable ni reproducible).

## R-06 — Extraccion cualitativa: puerto, proveedor gestionado y versiones

**Decision**: la extraccion cualitativa usa un puerto de dominio
`StructuredExtractor` con un adapter real a proveedor externo gestionado
(clarificacion 2026-08-06; FR-014) y un fake de prueba (patron ImportSource
de H2.1). Cada concepto cualitativo declara un schema permitido en el contrato
`extraction-v1`; el adapter solo recibe el input permitido (proyeccion
determinista de campos autorizados, nunca PII de usuarios ni raw HTML,
FR-014/FR-018-embeddings). Los outputs invalidos se rechazan o reintentan con
un maximo acotado (settings, default 2) y los fallos quedan consultables como
observaciones `failed` con `failure_code` (FR-012). Todo modelo, prompt y
schema se registra en `extraction_versions` (immutables) y cada observacion
generativa referencia su version exacta (FR-013, SC-003/SC-006). La eleccion
de proveedor concreto y costos se decide en el ADR del plan (el puerto, el
versionado y el registro de uso son lo exigido por la spec).

**Rationale**: el puerto aislado mantiene el dominio libre de clientes de LLM
(constitucion III); la validacion contra schema del contrato + reintento
acotado + fallo consultable cubre FR-011/FR-012 sin infraestructura
especulativa.

**Alternatives**: modelo autohospedado (rechazado por la clarificacion: costo y
operacion no justificados para beta); solo fake y diferir a H4 (rechazado:
UM-H3-007 es P0 y necesita el camino real verificado); dependencia de
schemas/validacion tipo jsonschema nueva (rechazado: validacion a mano contra
el contrato, sin dependencia nueva).

## R-07 — Recomputacion selectiva: invalidacion automatica + recomputo manual

**Decision**: (clarificacion 2026-08-06) dos pasos separados. (1)
Invalidacion automatica al registrarse un cambio de version (nueva
`concept_versions`, nueva `extraction_versions` de prompt/modelo/schema, o
nuevo `normalizer_version` de parser en Silver): el servicio marca las
observaciones afectadas `active -> invalidated` sin tocar las demas (FR-015).
(2) Recomputo manual: el operador dispara el job `extraction.recompute` con
scope (`concept:<key>`, `extraction:<version_id>`, `parser:<normalizer_version>`
o `full`) y causa; el handler re-extrae el alcance, publica las nuevas
observaciones y supersede las invalidadas en una sola transaccion, registrando
el run en `recomputation_runs` con estado, conteos, causa y tiempos (FR-016).
Las observaciones invalidadas nunca se usan en resultados nuevos (FR-017).

**Rationale**: la invalidacion automatica es lo unico que hace cumplible
FR-017 sin depender de la disciplina del operador; el recomputo manual evita
jobs sorpresivos de costo variable (proveedor gestionado). El registro en
`recomputation_runs` da auditoria (SC-009).

**Alternatives**: recomputo automatico al cambiar version (rechazado por la
clarificacion: jobs costosos inesperados); invalidacion manual (rechazado:
deja ventana de uso de datos obsoletos).

## R-08 — Lineage y reproducibilidad

**Decision**: el lineage de una observacion es: observacion ->
`extraction_versions` (regla o modelo/prompt/schema) -> `silver_listings`
(listing + `normalizer_version` + `snapshot_id`) -> snapshot Bronze
(reutilizando el lineage Silver existente) (FR-023, SC-006). El input
permitido de cada extraccion es reproducible por construccion: proyeccion
determinista de campos del listing + version de extraccion (FR-013).

**Rationale**: el guardrail de lineage completo (100%) exige este recorrido
consultable; reutilizar el lineage Silver evita duplicar la cadena Bronze.

**Alternatives**: guardar una copia del input en cada observacion (rechazado:
duplica datos; la proyeccion + version es reproducible).

## R-09 — Eventos de auditoria sobre el registry existente

**Decision**: se agregan 4 tipos de evento al registry cerrado
`contracts/events/v1` (aditivo, no rompe v1): `criteria.concept_version_created.v1`,
`criteria.compilation_created.v1`, `criteria.observation_batch_published.v1`,
`criteria.recompute_completed.v1` (FR-022, SC-010). Se emiten desde el servidor
en la misma transaccion del cambio (patron de 004). Los payloads llevan solo
ids, versiones y conteos; nunca fragmentos de texto, valores de observaciones,
pesos ni PII (forbidden keys existentes del registry).

**Rationale**: reutiliza la tabla `product_events` y la validacion ya
implementada; los conteos son derivables de las filas committeadas sin duplicar
datos sensibles.

**Alternatives**: telemetria solamente (rechazado: no auditable a nivel
producto); evento por observacion individual (rechazado: volumen; el batch
summary es suficiente y acotado).

## R-10 — Embeddings (P1): indice separado con version y regeneracion selectiva

**Decision**: los embeddings viven en `listing_embeddings` (P1, UM-H3-009):
una fila por (listing, version de modelo) con vector pgvector, estado y
version FK a `extraction_versions` (kind=`embedding`). El input es la misma
proyeccion permitida de campos del listing normalizado (FR-018: nunca raw HTML
ni PII). Un cambio de modelo o de texto permitido regenera solo los embeddings
afectados via recomputo selectivo, conservando las versiones previas (FR-019).
`embeddings.enabled` default false: no bloquea el camino critico.

**Rationale**: pgvector ya esta provisionado (H1-007) y la dimension se fija
por config; la regeneracion selectiva reutiliza el mecanismo de R-07.

**Alternatives**: embeddings en la fila del listing (rechazado: mezcla datos
Gold con Silver y complica versiones); re-embedding total en cada cambio
(rechazado: viola FR-019).

## R-11 — Contexto urbano (P1): senales versionadas con cache

**Decision**: `urban_signals` (P1, UM-H3-010) persiste por listing: tipo de
senal (`cafe` | `transport` | `green_space`), fuente, fecha de observacion,
geometria (Point 4326, respetando la precision autorizada del listing),
version de algoritmo y payload acotado (FR-020). Las consultas externas se
sirven con cache (tabla de cache o Redis existente) y respetan los limites de
la fuente (FR-021). `urban.context_enabled` default false.

**Rationale**: la fuente externa es optativa para beta; el registro de fuente/
fecha/geometria/algoritmo es lo que hace auditable cada senal (SC-008).

**Alternatives**: embeder senales en observaciones (rechazado: son hechos
geograficos, no observaciones de concepto); sin cache (rechazado: costos y
rate limits de la fuente).

## R-12 — Sin superficie HTTP ni cambios de policy en este incremento

**Decision**: no se agregan routers, no se toca `domain/identity/policy.py` y
no se regenera el cliente web (clarificacion 2026-08-06; FR-024). El consumo
de conceptos, criterios y observaciones lo haran por dominio el scoring H3.2,
los jobs y el harness; los preference facts y ediciones se crean con el
servicio de dominio desde el harness (supuesto del spec). El OpenAPI queda
intacto (mayor 1, aditivo).

**Rationale**: el backlog de H3.1 no pide superficie; la consola operativa es
H6 y el chat H4. Menos superficie = menos superficie de ataque y menos
contratos que mantener.

**Alternatives**: API interna de operacion (rechazado por la clarificacion);
API de lectura de observaciones (rechazado: el consumidor es el motor por
dominio).

## Decisiones diferidas a fases posteriores (registradas)

- Proveedor concreto de extraccion cualitativa, dimension y modelo de
  embeddings: ADR del plan; el puerto y el versionado son lo exigido.
- Evaluadores de matcher types (numeric range, categorical, geo proximity,
  semantic feature): H3.2 (UM-H3-013); este incremento solo registra y valida
  tipos y parametros.
- Conversion de feedback en preference facts/propuestas: H3.3 (UM-H3-028).
- Superficie de curaduria y consola operativa: H6.
- Umbral temporal de recomputo: target practico del harness (< 30 s sobre el
  conjunto de prueba), no un SC del spec.
