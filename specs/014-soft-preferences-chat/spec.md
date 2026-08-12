# Feature Specification: Criterios suaves activos y chat de preferencias

**Feature Branch**: `014-soft-preferences-chat`

**Created**: 2026-08-12

**Status**: Draft

**Input**: User description: "Activar la capa de criterios suaves (conceptos, observaciones, preference facts) para que el radar deje de ser solo filtros duros y estáticos, y permitir que el usuario exprese preferencias suaves en el chat (luminosidad, balcón, tipo de cocina, estado general, ambientes, piso) con confirmación explícita, guardado como hechos auditables y recomputación del ranking."

## Operational Definitions

- **Concepto**: característica evaluable de un listing (luminosidad, balcón, tipo de cocina, estado general, ambientes, piso) definida en un catálogo versionado con matcher, aliases y política de datos faltantes.
- **Observación**: valor extraído de un listing para un concepto, con evidencia (fragmento del texto o campo que lo sustenta), confianza, fuente (regla o modelo) y versión del artefacto de extracción.
- **Hecho de preferencia (fact)**: preferencia del usuario sobre un concepto (polaridad, peso, confianza, fuente, fecha), versionada por perfil; la fuente de verdad de lo que el usuario quiere.
- **Compilación de criterios**: criterios ejecutables (duros del perfil + suaves desde facts) generados por versión de perfil; entrada determinística del scoring.
- **Propuesta de preferencia**: cambio de preferencia propuesto desde el chat, durable y pendiente de confirmación explícita del usuario (mismo patrón HITL de los cambios de perfil).
- **Recomputación**: nuevo run de scoring sobre el perfil y los criterios actualizados tras confirmar una preferencia.

## Review and Measurement Protocol

- La puerta de salida cierra el incremento `soft-preferences-chat`: catálogo de conceptos y extracción sembrados y versionados, observaciones con evidencia publicadas, compilación con criterios suaves, scoring y explicaciones que citan evidencia, chat que propone preferencias canónicas con confirmación HITL, facts auditables con fuente "chat" y recomputación.
- La extracción se verifica con casos golden determinísticos: misma versión de contratos + mismos listings → mismas observaciones (reglas 100% determinísticas; cualitativas con valor, evidencia, confianza y versión).
- Las propuestas del chat se verifican con contract tests del tool y evals golden de conversación: la intención natural se mapea a conceptos canónicos por código (0 adivinanza del LLM sobre valores), toda mutación exige confirmación e idempotencia, y los errores (concepto inexistente, contradicción, dato faltante) tienen respuestas accionables.
- La recomputación se verifica: al confirmar una preferencia, el nuevo run referencia el fact y la versión de perfil actualizados; el ranking cambia según la política de scoring versionada.
- El seed local deja el stack completo activo con un comando (conceptos, extracción, compilación y run con criterios suaves) y los checks se integran al harness (`check-criteria.ps1`, `check-chat.ps1`, `check-agent.ps1`).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Radar que considera preferencias suaves (Priority: P1)

Como usuario de la beta, quiero que mi radar considere cosas como luminosidad, balcón o estado del edificio, y que me explique por qué un depto me encaja citando esa evidencia, para confiar en las recomendaciones más allá del precio y la zona.

**Why this priority**: Sin la capa suave activa el producto es solo filtros duros; esta historia es la base de todo lo demás (Fase 0 del roadmap).

**Independent Test**: Con el catálogo sembrado y la extracción corrida, un perfil con una preferencia de luminosidad devuelve matches rankeados considerándola y cada explicación cita la evidencia de la observación.

**Acceptance Scenarios**:

1. **Given** el catálogo de conceptos y las versiones de extracción sembrados, **When** se corre la extracción sobre los listings, **Then** cada listing tiene observaciones activas por concepto con valor, confianza, evidencia, fuente y versión.
2. **Given** un perfil con un fact de preferencia (p.ej. luminosidad positiva), **When** se compila y corre un run, **Then** los criterios suaves participan del score y la explicación del match cita la observación que la sustenta.
3. **Given** un listing sin datos para un concepto con política "exclude", **When** se corre el run, **Then** el listing no se puntúa por ese concepto y la explicación declara el dato faltante.

### User Story 2 - Preferencia suave expresada en el chat (Priority: P1)

Como usuario, quiero decirle a Umbral en el chat "quiero un depto luminoso" o "prefiero con balcón" y que, tras confirmar, el radar adopte esa preferencia y me muestre resultados que la reflejen.

**Why this priority**: Es el corazón del roadmap (Fase 1): el lenguaje natural conectado a la maquinaria de preferencias con código auditable.

**Independent Test**: Un usuario expresa una preferencia suave en el chat, la confirma en el flujo HITL, y el siguiente run refleja la preferencia con un fact persistido de fuente "chat".

**Acceptance Scenarios**:

1. **Given** una conversación activa, **When** el usuario dice "quiero un depto luminoso", **Then** el agente propone un cambio de preferencia sobre el concepto luminosidad con polaridad positiva, sin aplicar nada todavía.
2. **Given** una propuesta de preferencia pendiente, **When** el usuario la confirma, **Then** se registra un fact con fuente "chat", se recompila el perfil y se recomputa el ranking.
3. **Given** una propuesta de preferencia, **When** el usuario la rechaza, **Then** no se registra ningún fact y el perfil no cambia.
4. **Given** el usuario repite la misma preferencia confirmada, **When** el agente propone de nuevo, **Then** el sistema no duplica el fact y responde que ya está vigente.

### User Story 3 - Revisar y remover preferencias suaves (Priority: P2)

Como usuario, quiero ver qué preferencias suaves tiene mi radar (qué, cuándo y con qué fuente se aprendió) y poder quitar una, para mantener el control de lo que Umbral cree que me gusta.

**Why this priority**: Sin visibilidad ni control, las preferencias aprendidas generan desconfianza; es la contracara de la audibilidad (Constitución II/V).

**Independent Test**: Un usuario lista las preferencias vigentes de su radar, identifica su fuente, y remueve una; el siguiente run deja de considerarla.

**Acceptance Scenarios**:

1. **Given** un radar con facts vigentes, **When** el usuario consulta sus preferencias, **Then** ve cada concepto con polaridad, fuente, fecha y estado.
2. **Given** una preferencia vigente, **When** el usuario la remueve, **Then** el fact queda superseded con trazabilidad y el siguiente run no la considera.
3. **Given** una preferencia removida, **When** el usuario pregunta por ella, **Then** el sistema responde que no está vigente.

### User Story 4 - Contradicción entre preferencias (Priority: P3)

Como usuario, quiero que Umbral detecte cuando le pido lo opuesto de una preferencia vigente, para no terminar con criterios contradictorios silenciosamente.

**Why this priority**: Evita que el ranking se vuelva inconsistente sin aviso (Constitución II).

**Acceptance Scenarios**:

1. **Given** un fact vigente de luminosidad negativa, **When** el usuario pide "quiero algo luminoso", **Then** el agente pregunta cómo dejar la preferencia en vez de aplicar el cambio a ciegas.
2. **Given** una contradicción detectada, **When** el usuario confirma que quiere cambiar la preferencia, **Then** el fact anterior queda superseded y el nuevo se registra con su fuente.

### Edge Cases

- El usuario pide una preferencia sobre un concepto que no está en el catálogo → rechazo accionable: se explica qué conceptos existen y no se inventa nada.
- El usuario expresa una preferencia sin polaridad clara ("que no sea tan oscuro") → clarificación acotada antes de proponer.
- Un listing no tiene datos para el concepto de la preferencia → se aplica la política de datos faltantes versionada del concepto y la explicación lo declara.
- La extracción con modelo falla para un listing → observación en estado failed con código, sin romper el run ni el resto del batch.
- La confirmación llega vencida o duplicada → se aplican las reglas de idempotencia y expiración de propuestas existentes.
- El usuario no tiene ninguna preferencia y pregunta "qué te gusta de mí" → respuesta honesta: todavía no hay preferencias aprendidas.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST poder sembrar el catálogo de conceptos y las versiones de extracción desde los contratos publicados, de forma idempotente y versionada.
- **FR-002**: El sistema MUST extraer observaciones por concepto sobre los listings del radar (reglas determinísticas + extracción estructurada con evidencia y confianza para conceptos cualitativos) y publicarlas con invalidación selectiva al cambiar versiones.
- **FR-003**: La compilación de criterios de un perfil MUST incluir los criterios suaves derivados de los facts vigentes, junto a los filtros duros, de forma versionada.
- **FR-004**: El scoring MUST consumir los criterios compilados (duros y suaves) de forma determinística y versionada, y las explicaciones de los matches MUST citar la evidencia de las observaciones cuando exista.
- **FR-005**: El chat MUST reconocer el vocabulario canónico de preferencias (luminosidad, balcón, tipo de cocina, estado general, ambientes, piso) y traducirlo a conceptos del catálogo por código determinístico, sin que el modelo decida valores ni campos.
- **FR-006**: Toda preferencia propuesta desde el chat MUST pasar por confirmación explícita (HITL) con propuesta durable, idempotencia y expiración.
- **FR-007**: Al confirmar una preferencia, el sistema MUST registrar un hecho de preferencia con fuente "chat", polaridad, peso y confianza, recomilar criterios y recomputar el ranking.
- **FR-008**: El usuario MUST poder listar las preferencias suaves vigentes de su radar (concepto, polaridad, fuente, fecha) y remover una, dejando trazabilidad de la supersesión.
- **FR-009**: El sistema MUST detectar contradicciones entre una preferencia pedida y los facts vigentes, y preguntar antes de aplicar.
- **FR-010**: El seed local MUST activar el stack completo (conceptos, extracción, compilación con criterios suaves y un run) con un comando único y verificable.

### Key Entities

- **Concept / ConceptVersion**: catálogo versionado de características evaluables con matcher, aliases, defaults y política de datos faltantes.
- **ListingObservation**: valor observado de un listing para un concepto, con evidencia, confianza, fuente, versión y estado (activa/invalidada/superseded/failed).
- **PreferenceFact**: preferencia vigente del usuario sobre un concepto, con polaridad, peso, confianza, fuente y estado (activa/superseded).
- **ProfileCriteriaCompilation**: criterios ejecutables (duros + suaves) por versión de perfil.
- **PreferenceProposal**: propuesta durable de cambio de preferencia pendiente de confirmación, con diff, impacto, expiración e idempotencia.
- **RecommendationRun / RecommendationItem**: ejecución de scoring sobre perfil y criterios versionados, y los matches persistidos con score y posición.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Un usuario sin datos previos puede dejar una preferencia suave confirmada desde el chat en menos de 5 turnos y ver un ranking nuevo que la refleja.
- **SC-002**: 100% de los cambios de preferencia desde el chat pasan por confirmación explícita y quedan registrados con fuente, versión y fecha auditables.
- **SC-003**: Las explicaciones de los matches citan evidencia para al menos el 80% de las razones basadas en observaciones activas.
- **SC-004**: La extracción es reproducible: misma versión de contratos + mismos listings → mismas observaciones (verificación golden por regla y por concepto cualitativo).
- **SC-005**: Al confirmar una preferencia, el nuevo run de recomendación referencia el fact y la versión de perfil actualizados, y el ranking cambia según la política de scoring versionada.

## Assumptions

- La Fase 3 del roadmap (nuevos conceptos: moderno, proximidad a cafés, transporte) queda fuera de alcance; este incremento usa el catálogo actual (luminosidad, balcon, tipo_cocina, estado_general, ambientes, piso).
- Embeddings y urban signals siguen en P1; este incremento no los habilita.
- La confirmación HITL reusa el patrón de propuestas de cambio de perfil existente (propuesta durable + decisión + aplicar).
- El peso y la confianza de los facts propuestos por chat usan los defaults de la política de aprendizaje vigente.
- Las notificaciones proactivas (Fase 4) no cambian en este incremento.
- El seed local y el harness son la vía de verificación; las integraciones con Postgres corren con Docker levantado.
