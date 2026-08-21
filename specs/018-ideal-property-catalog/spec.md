# Feature Specification: Catalogo del inmueble ideal con fuerza por usuario

**Feature Directory**: `specs/018-ideal-property-catalog`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "Al describir el inmueble ideal, el usuario produce deseos que hoy se pierden porque no hay un concepto evaluable para buena parte de lo que dice (dormitorios, mascotas, amenities del edificio) ni señales urbanas para educación, deporte, cultura o bici. Además, un mismo criterio puede ser solo un plus para una persona y un requisito excluyente para otra: el sistema debe dejar que cualquier criterio estructurado sea soft o hard por usuario, con confirmación y trazabilidad, y guiar la conversación cuando un deseo no es evaluable."

## Operational Definitions

- **Concepto**: característica compartida de una vivienda o su entorno que Umbral observa y evalúa con una semántica versionada (`CONTEXT.md`).
- **Deseo expresado**: formulación completa y contextual de lo que la persona busca o evita, sea o no evaluable.
- **Vinculación de criterio**: interpretación versionada que relaciona un deseo expresado con cero, una o varias capacidades evaluables.
- **Hecho de preferencia**: interpretación estructurada y vigente de la parte computable de un deseo para un radar.
- **Preferencia suave**: deseo computable que modifica el orden relativo de oportunidades sin excluirlas.
- **Filtro duro**: condición binaria, explícita y auditable que excluye oportunidades del conjunto candidato.
- **Modo de fuerza (soft/hard)**: atributo por radar de un criterio estructurado que decide si el criterio reordena (`soft`) o excluye (`hard`) candidatos.
- **Señal urbana**: valor factual de entorno de una vivienda declarado en el contrato urbano y calculado a partir de un snapshot.

## Relationship to Existing Features

Esta feature extiende los catálogos de `005-criteria-observations`, `014-soft-preferences-chat`, `015-catalog-concept-expansion` y `017-urban-signals`: agrega conceptos de vivienda y señales urbanas nuevas, y completa el seam dormido de `016-conversational-search-copilot`/`preferences` para que `BindingDraft.mode` y `CompiledCriterion.soft_to_hard` se produzcan y se ejecuten de verdad. Conserva objetos persistentes, auditoría, scoring determinista y evidencia; no cambia la ingesta Bronze/Silver ni las notificaciones.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Describir la vivienda ideal con conceptos que ya existen (Priority: P1)

Como persona que busca alquilar en CABA, quiero que lo que digo del inmueble ("2 dormitorios", "aceptan mascotas", "con ascensor") se convierta en un hecho de preferencia utilizable, para no repetirlo ni verlo ignorado.

**Why this priority**: el objetivo central es reducir los deseos sin contribución; estos conceptos son los de mayor frecuencia en el mercado.

**Independent Test**: una persona expresa "quiero 2 dormitorios, que acepten mascotas y que tenga ascensor" y el radar conserva los tres como hechos computables con evidencia, sin que ningún deseo quede sin contribución por falta de concepto.

**Acceptance Scenarios**:

1. **Given** un radar activo, **When** la persona dice "quiero al menos 2 dormitorios", **Then** se crea el hecho `dormitorios` con valor mínimo 2 y contribuye al scoring.
2. **Given** una búsqueda normalizada con campo `bedrooms`, **When** se ejecuta la extracción, **Then** la observación `dormitorios` se produce por regla determinística desde el dato estructurado.
3. **Given** un anuncio que declara "acepta mascotas", **When** se consulta su observación, **Then** el concepto `mascotas` se observa como `true` con fracción de evidencia.
4. **Given** un anuncio con amenities que incluyen "cochera cubierta", **When** se consultan las observaciones, **Then** el concepto `cochera` se observa como `true` con la amenity como evidencia.
5. **Given** un deseo de "baños" sin dato estructurado, **When** se ejecuta la extracción, **Then** se observa por modelo con schema versionado y confianza declarada.

---

### User Story 2 - Describir el entorno con señales urbanas nuevas (Priority: P1)

Como persona que valora el barrio, quiero que frases como "cerca de una escuela", "con gimnasio cerca" o "para moverme en bici" impacten la búsqueda, para que el entorno deje de ser solo cafés y subte.

**Why this priority**: el contrato urbano ya fue diseñado para esto (US3 de 017); cerrar el loop convierte el mecanismo en valor real por usuario.

**Independent Test**: una persona expresa "quiero estar cerca de una escuela" y el radar produce una preferencia `acceso_escuela` evaluable por la señal urbana correspondiente, con unknown honesto cuando no hay datos.

**Acceptance Scenarios**:

1. **Given** un snapshot urbano importado, **When** se calculan señales, **Then** las señales nuevas (`accesso_escuela`, `accesso_deporte`, `accesso_cultura`, `accesso_bici`, `accesso_salud`) se computan por contrato sin cambios en el engine de scoring.
2. **Given** una frase "cerca de una escuela", **When** se vincula, **Then** apunta a un concepto con `signal_ref` y produce observación con score, confidence y contributors.
3. **Given** un barrio con pocas muestras para una señal, **When** se normaliza, **Then** la señal cae al fallback CABA con confianza penalizada (×0.7) o queda `unknown`, nunca inventa un valor medio.
4. **Given** un deseo "quiero salud cerca", **When** se vincula, **Then** se reutiliza la categoría `health` ya existente como señal `accesso_salud` sin duplicar primitivas.

---

### User Story 3 - Que cualquier criterio sea soft o hard por usuario (Priority: P1)

Como persona con necesidades distintas según la búsqueda, quiero que "balcón sí o sí" excluya y "balcón si lo tiene" reordene, sin que el sistema asuma uno por mí, para que mis requisitos reales se respeten y mis gustos solo ponderen.

**Why this priority**: la fuerza del criterio es parte de la descripción del inmueble ideal; hoy no existe ningún camino ejecutable para expresarla.

**Independent Test**: un usuario convierte un criterio estructurado a hard con confirmación y el motor excluye a los candidatos que no cumplen; otro usuario mantiene el mismo criterio soft y los candidatos se reordenan pero no se excluyen.

**Acceptance Scenarios**:

1. **Given** un deseo expresado con wording de exclusión ("tiene que tener ascensor sí o sí"), **When** el copiloto lo interpreta, **Then** propone un binding con `mode=hard` y solicita confirmación antes de aplicarlo.
2. **Given** una confirmación registrada para ese concepto, **When** se compilan los criterios, **Then** `soft_to_hard=True` se propaga al compilador y el engine excluye en `mismatch`.
3. **Given** un deseo con wording de preferencia ("si tiene terraza es un plus"), **When** se interpreta, **Then** el binding queda `mode=soft` sin confirmación y contribuye solo al ordenamiento.
4. **Given** una polaridad negativa ("no quiero balcón") con hard, **When** se evalúa un candidato con balcón, **Then** se excluye; sin balcón, pasa.
5. **Given** un concepto semántico (p.ej. `moderno`), **When** el usuario pide convertirlo a hard, **Then** se rechaza por diseño: los semánticos solo son soft con confianza visible.
6. **Given** un hard con señal urbana (p.ej. "escuela cerca sí o sí"), **When** se confirma, **Then** se propone un umbral percentil explícito y la señal por debajo del umbral excluye.

---

### User Story 4 - Entender qué se entendió y qué no (Priority: P2)

Como persona que describe su ideal, quiero recibir feedback honesto sobre qué de lo que dije se usó, qué quedó sin evidencia y por qué, para completar la descripción sin adivinar.

**Why this priority**: el corazón del objetivo es la transparencia del mapeo; sin retroalimentación el usuario no sabe qué faltó decir.

**Independent Test**: un deseo no evaluable se conserva con una explicación del límite y un puente sugerido hacia conceptos cercanos evaluables.

**Acceptance Scenarios**:

1. **Given** un deseo sin concepto evaluable, **When** el usuario lo expresa, **Then** se conserva como deseo sin contribución y el copiloto explica el límite y sugiere un concepto cercano ("buena onda → ¿te sirve caminabilidad o vida nocturna?").
2. **Given** un concepto con observación `unknown`, **When** se muestra la preferencia, **Then** la UI declara la ausencia de datos y baja la confianza en vez de mostrar un valor medio.
3. **Given** un radar con filtros hard nuevos que deja cero candidatos, **When** se ejecuta la búsqueda, **Then** se persisten diagnostics con las relajaciones sugeridas y un evento auditable; no se bloquea la acción del usuario.

### Edge Cases

- El usuario mezcla hard y soft para el mismo concepto en distintas frases (la última con confirmación prevalece con trazabilidad).
- Un concepto semántico se intenta elevar a hard.
- Una señal urbana con categoría rara deja la mayoría de listings en `unknown`.
- Un hard deja el set de candidatos vacío.
- Una hipótesis aprendida existencia para el concepto que se eleva a hard.
- Un cambio de contrato urbano invalida observaciones previas mientras hay un hard activo dependiente de esa señal.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El catálogo de conceptos MUST incluir los conceptos de vivienda `dormitorios`, `baños`, `mascotas`, `amoblado`, `ascensor`, `cochera` y `piscina`, versionados como `concepts-v2`.
- **FR-002**: El concepto `dormitorios` MUST ser distinto de `ambientes` y leer el campo normalizado `bedrooms` del Silver.
- **FR-003**: La extracción MUST ser determinística cuando existe dato estructurado (dormitorios, amenities) y de modelo con schema versionado solo para lo difuso (baños, mascotas, amoblado desde texto).
- **FR-004**: El contrato urbano MUST incorporar las señales `accesso_escuela`, `accesso_deporte`, `accesso_cultura`, `accesso_bici` y `accesso_salud` como `urban-contract-v2`, sin cambios al engine de scoring ni a los workers de criterios.
- **FR-005**: Cada señal nueva MUST generar observaciones por concepto con `signal_ref`, score, confidence y contributors según la convención de `017-urban-signals`.
- **FR-006**: Un deseo con wording de exclusión MUST proponer un binding con `mode=hard` y requerir confirmación (`HardConfirmationRef`) antes de aplicarse.
- **FR-007**: Un deseo con wording de preferencia MUST crear un binding `mode=soft` sin confirmación.
- **FR-008**: El compilador MUST propagar el `mode` del binding al `CompiledCriterion.soft_to_hard` y el engine MUST excluir candidatos cuyo resultado sea `mismatch` en un criterio con `soft_to_hard=True`.
- **FR-009**: Los conceptos semánticos/cualitativos MUST permanecer siempre soft y MUST NOT admitir elevación a hard.
- **FR-010**: La polaridad negativa combinada con hard MUST excluir la presencia del atributo ("no quiero balcón" excluye con balcón) y MUST excluir su ausencia para el caso negativo de una señal con umbral.
- **FR-011**: Un hard sobre una señal urbana MUST fijar un umbral cuantitativo (percentil) propuesto y confirmado por el usuario.
- **FR-012**: La elevación a hard MUST registrar un evento auditable y MUST retirar o superar toda hipótesis de preferencia activa del mismo concepto con trazabilidad.
- **FR-013**: El learning/feedback MUST NOT generar ni superar facts con `soft_to_hard=True`; los hard solo nacen de declaración explícita confirmada.
- **FR-014**: Ante un set de candidatos vacío causado por criteria hard, MUST persistirse diagnostics con relajaciones sugeridas (`raise_budget`, `widen_zones`, `lower_rooms` o el criterio responsable) y un evento; el UX de "radar agotado" queda fuera de esta feature.
- **FR-015**: Un deseo no evaluable MUST conservarse con su formulación original y el copiloto MUST explicar el límite y sugerir un concepto evaluable cercano.
- **FR-016**: Los conceptos y señales nuevos MUST exponerse en el vocabulario de preferencias para que la auto-detección del copiloto los proponga.
- **FR-017**: El `mode` hard/soft MUST persistir por radar (profile), no global; solo se aplica al radar donde se confirmó.
- **FR-018**: Los contratos v1 existentes MUST quedar intactos; las versiones nuevas superseden e invalidan lo anterior por el lifecycle ya existente.
- **FR-019**: La tasa de mapeo conversacional MUST medirse con trayectorias extendidas y cobertura de observaciones activas por concepto.

### Key Entities

- **Concepto**: vivienda (dormitorios/baños/mascotas/amoblado/ascensor/cochera/piscina) y urbano (accesso_escuela/accesso_deporte/accesso_cultura/accesso_bici/accesso_salud).
- **Hecho de preferencia**: un criterio estructurado para un radar con valor, peso, polaridad, confianza y fuente.
- **Criterio compilado**: condición validada con `soft_to_hard` y referencias a su binding/fact.
- **Señal urbana**: valor factual de entorno con scoring, confidence y contributors.
- **Evento de elevación a hard**: cambio auditable de un criterio de soft a hard con confirmación y supersesión de hipótesis.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Al menos el 90% de los deseos expresados en la suite de aceptación para los conceptos nuevos termina como hecho computable con evidencia activa.
- **SC-002**: El 100% de las trayectorias de conversación nuevas para los conceptos nuevos alcanza el estado durable esperado (tasa de mapeo ≥80% en agregado).
- **SC-003**: Un hard confirmado excluye de forma determinista y verificable por test al 100% de los candidatos en `mismatch`.
- **SC-004**: Las señales v2 se computan y se exponen en el batch urbano sin cambios al engine de scoring ni a los workers de criterios.
- **SC-005**: La cobertura de observaciones activas por concepto nuevo alcanza al menos el 60% de los listings con geo_precision exacta/block en staging.
- **SC-006**: Ningún concepto semántico se eleva a hard en toda la ejecución de aceptación.
- **SC-007**: Cero regresiones no declaradas en el golden de matching tras agregar las señales v2.
- **SC-008**: El 100% de los radares vacíos por hard recibe diagnostics + evento; ninguno queda silenciosamente sin explicación.

## Assumptions

- La beta sigue enfocada en alquileres residenciales en CABA.
- El orden final, los filtros duros y las decisiones de notificación permanecen deterministas y versionados.
- El hard se aplica por radar; no existe un perfil global del usuario en esta feature.
- Los conceptos semánticos no pueden ser hard porque su observación es una lectura de baja confianza sin dato estructurado.
- `bedrooms` ya está normalizado en Silver; agregarlo a `allowed_input_fields` no requiere migración de esquema.
- Las categorías `health` y `green_space` ya existen; `accesso_salud` y otras nuevas se declaran en el contrato v2 (JSON), con señalizacion de nodos vs ways según corresponda.
- Las señales con cobertura baja degradan a `unknown` o percentil 0.5 con confianza ×0.7; es un resultado honesto, no un error.

## Out of Scope

- Infraestructura de anclas de usuario, tiempos de viaje y geocoding de puntos de referencia (bloque C).
- Exclusiones de zona negativas en el perfil (`zones` sigue siendo whitelist).
- Prioridad relativa/ pesos por usuario sobre preferencias.
- UX de "radar agotado" y notificaciones de vacío.
- Cambios a ingesta Bronze/Silver, notificaciones o identity.
- Convertir señales semánticas o cualitativas en hard filters.