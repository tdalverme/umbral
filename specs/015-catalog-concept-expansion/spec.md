# Feature Specification: Expansión del catálogo de conceptos (Fase 3)

**Feature Branch**: `015-catalog-concept-expansion`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Expandir el catálogo de conceptos del radar para que el chat entienda más preferencias naturales (moderno, cerca de cafés, buen transporte) y que el ranking las considere. La estrategia debe ser robusta pero flexible: agregar un concepto nuevo debe ser solo datos versionados + un golden de calidad, sin tocar el pipeline."

## Operational Definitions

- **Concepto**: característica evaluable de un listing (matcher, aliases, política de datos faltantes, schema de extracción) declarada en el catálogo versionado.
- **Tipo de concepto**: la familia de extracción/evaluación que define cómo se obtiene el valor: regla (texto/campos), modelo cualitativo (schema enum + evidencia + confianza) o señal urbana (señales versionadas → observación con proxy).
- **Proxy**: decisión versionada que traduce una señal cruda (p.ej. cantidad de cafés en un radio) en un valor de concepto; se declara y versiona con el concepto, nunca se esconde.
- **Golden de extracción**: casos etiquetados que fijan la salida esperada del extractor por concepto (regla o modelo) y gatean la publicación del concepto.
- **Observación urbana**: observación con `source = urban` que consolida señales versionadas de un listing en un valor de concepto (mismo canal que las observaciones de texto/modelo para el scoring).

## Review and Measurement Protocol

- La puerta de salida cierra el incremento: el pipeline soporta los tres tipos de concepto sin cambios por concepto nuevo; el peso de los hechos de preferencia viaja en la compilación; las señales urbanas se consolidan en observaciones con proxy versionado; el chat propone los conceptos nuevos con el vocabulario canónico sin código adicional; cada concepto nuevo entra con un golden de extracción que gatea su publicación.
- Se verifica con dos casos de validación completos: un concepto cualitativo ("moderno") y un concepto urbano ("proximidad a cafés") recorriendo catálogo → extracción → observación → compilación → scoring → explicación → chat, con sus golden.
- Los checks se integran al harness (golden de extracción por concepto, scoring golden, evals del chat).
- La estrategia se valida con la regla: agregar un concepto = contrato (seed + extracción + vocabulario) + golden; el código del pipeline no cambia.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agregar un concepto cualitativo sin tocar el pipeline (Priority: P1)

Como equipo de producto, quiero agregar "moderno" al catálogo con solo datos versionados y un golden de calidad, para que el chat lo proponga y el ranking lo considere sin cambios de código.

**Why this priority**: Valida la promesa central de la estrategia (catálogo data-driven) con el tipo más barato.

**Independent Test**: Se agrega "moderno" al catálogo (seed + schema + vocabulario + golden) y el flujo completo funciona: extracción con evidencia, compilación, ranking con polarity, explicación y propuesta en el chat.

**Acceptance Scenarios**:

1. **Given** el concepto "moderno" declarado en el catálogo con schema enum (`clasico|renovado|moderno`), **When** corre la extracción, **Then** cada listing tiene una observación con valor, score derivado del enum, confianza, evidencia y versión.
2. **Given** un usuario con preferencia "moderno" (positiva), **When** se recomputa, **Then** el ranking premia a los listings modernos y la explicación cita la evidencia.
3. **Given** la frase "quiero algo moderno", **When** el usuario la escribe en el chat, **Then** el agente propone la preferencia sin cambios de código (vocabulario canónico).

### User Story 2 - Agregar un concepto urbano con proxy versionado (Priority: P1)

Como equipo de producto, quiero que "cerca de cafés" sea un concepto derivado de las señales urbanas existentes, con un proxy (radio y umbral) declarado y versionado, para que el ranking lo considere sin tocar el engine.

**Why this priority**: Habilita el tercer tipo de concepto (el que no existe hoy) y valida que las señales urbanas lleguen al scoring.

**Independent Test**: Se agrega "proximidad_cafes" con su proxy; las señales cafe existentes se consolidan en observaciones urbanas; el ranking y la explicación las usan; el chat propone la preferencia.

**Acceptance Scenarios**:

1. **Given** señales urbanas `cafe` con geometría y `algorithm_version`, **When** corre la consolidación urbana, **Then** cada listing con señales en el radio del proxy tiene una observación activa con `source = urban` y evidencia que cita las señales.
2. **Given** una preferencia "cerca de cafés" (positiva), **When** se recomputa, **Then** el ranking premia a los listings con más señales según el proxy y la explicación cita las señales.
3. **Given** un cambio de proxy (radio), **When** se versiona el concepto, **Then** la invalidación selectiva afecta solo las observaciones urbanas de ese concepto.

### User Story 3 - El peso de la preferencia llega al ranking para cualquier concepto (Priority: P1)

Como usuario, quiero que cualquier preferencia que confirme tenga un peso real en el ranking, incluso para conceptos fuera de la política estática de scoring.

**Why this priority**: Brecha detectada: el peso del hecho no viaja en la compilación; los conceptos fuera del policy no puntúan.

**Independent Test**: Un fact de un concepto fuera del policy (p.ej. tipo_cocina o moderno) con peso 0.3 mueve el score del ranking en la dirección esperada.

**Acceptance Scenarios**:

1. **Given** un fact confirmado con peso propio, **When** se compila y recomputa, **Then** el criterio usa el peso del hecho (o el del policy como fallback) y el ranking cambia.
2. **Given** el mismo concepto con fact y sin fact, **When** se comparan los runs, **Then** el ranking difiere únicamente por el criterio del hecho.

### User Story 4 - Transporte como concepto genérico (Priority: P2)

Como usuario, quiero expresar "buen acceso a transporte" y que el radar lo considere como preferencia suave.

**Why this priority**: Completa el set inicial de la Fase 3 con el tipo urbano ya validado por cafés.

**Independent Test**: El concepto "acceso_transporte" se agrega con el mismo ciclo que cafés (señales transport) y funciona de punta a punta.

**Acceptance Scenarios**:

1. **Given** señales `transport`, **When** se consolida, **Then** las observaciones urbanas de transporte reflejan el proxy versionado.
2. **Given** "buen transporte" como preferencia, **When** se recomputa, **Then** el ranking y la explicación la reflejan.

### User Story 5 - Golden de extracción por concepto (Priority: P2)

Como equipo, quiero que cada concepto nuevo entre con casos etiquetados que gateen su calidad, para no publicar conceptos con extracción no validada.

**Why this priority**: Es el mecanismo que hace robusta la flexibilidad: sin gate de calidad, "solo datos" se convierte en "datos rotos".

**Independent Test**: Un concepto con golden que falla no se publica; con golden que pasa, se publica.

**Acceptance Scenarios**:

1. **Given** un golden de extracción con casos etiquetados, **When** corre el gate, **Then** el concepto se publica solo si supera el umbral (precision/recall) declarado.
2. **Given** una regresión en la extracción, **When** corre el harness, **Then** el golden falla y bloquea la publicación.

### Edge Cases

- Un concepto declara un matcher sin evaluador → validación estructural del contrato lo rechaza al sembrar.
- Un concepto de modelo sin schema → rechazo al sembrar.
- Un listing sin señales para un concepto urbano → observación `unknown` (política de datos faltantes del concepto) o `failed` con código si la consolidación falla.
- Cambio de proxy → invalidación selectiva del concepto, sin re-extraer los demás.
- El usuario pide "cafés lindos" → el proxy declarado (cantidad en radio) se aplica; la calidad ("lindos") queda fuera del concepto y se explica como limitación del proxy.
- Dos conceptos que solapan (p.ej. transporte y proximidad_cafes) → conviven; la explicación cita cada evidencia por separado.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST soportar los tres tipos de concepto (regla, modelo cualitativo, señal urbana) con el mismo ciclo de vida: catálogo → extracción/consolidación → observación → compilación → scoring → explicación → chat.
- **FR-002**: La compilación MUST incluir el peso del hecho de preferencia; el scoring MUST usar ese peso con fallback a la política estática cuando el concepto no esté declarado.
- **FR-003**: Las señales urbanas versionadas MUST consolidarse en observaciones con `source = urban`, proxy versionado (radio/umbral declarados en el contrato del concepto) y evidencia que cita las señales.
- **FR-004**: El scoring y las explicaciones MUST consumir las observaciones urbanas por el mismo canal que las de texto/modelo (0 cambios en el engine por concepto nuevo).
- **FR-005**: El chat MUST proponer los conceptos nuevos mediante el vocabulario canónico versionado, sin código adicional.
- **FR-006**: Cada concepto nuevo MUST publicarse con un golden de extracción (casos etiquetados + umbral) que gatee su entrada en producción.
- **FR-007**: Los cambios de proxy/versión de concepto MUST invalidar selectivamente solo las observaciones afectadas.
- **FR-008**: La validación estructural del contrato MUST rechazar conceptos con matcher, schema o política de datos faltantes incompletos.

### Key Entities

- **Concept / ConceptVersion**: catálogo versionado (seed) — ahora con tres fuentes de extracción: rule, model, urban.
- **UrbanSignal**: señal cruda versionada por listing (cafe/transport/green_space) con geometría y `algorithm_version`.
- **ListingObservation**: valor observado por concepto — incluye `source = urban` para las consolidadas.
- **PreferenceFact**: preferencia del usuario con peso propio que viaja en la compilación.
- **CompiledCriterion**: criterio ejecutable — ahora con weight del hecho cuando aplica.
- **ExtractionGolden**: casos etiquetados por concepto que gatean su publicación.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Agregar un concepto cualitativo ("moderno") y uno urbano ("proximidad_cafes") de punta a punta sin modificar el código del pipeline (solo contratos + golden).
- **SC-002**: El ranking de un run con un fact de un concepto fuera del policy difiere del run sin fact, en la dirección esperada por la polarity.
- **SC-003**: Las explicaciones de criterios urbanos citan las señales consolidadas (evidencia con versión de señal).
- **SC-004**: El golden de extracción gatea: un concepto cuyo golden falla no publica observaciones activas.
- **SC-005**: El chat propone "moderno" y "cerca de cafés" sin cambios de código del agente.

## Assumptions

- El costo dominante es el etiquetado/validación por concepto (golden), no el código.
- El proxy de cafés es cantidad de señales en un radio fijo versionado (V1); la calidad percibida ("lindos") queda fuera del concepto y se declara.
- El transporte V1 es genérico (presencia de señales transport en radio); la línea específica (subte D) queda fuera (requiere geometría de línea — filtro espacial, no concepto).
- Los conceptos nuevos entran de a uno, cada uno con su golden.
- El chat usa la tool existente de preferencias; solo crece el vocabulario.
