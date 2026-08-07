# Feature Specification: Feedback y aprendizaje controlado

**Feature Branch**: `007-feedback-learning`

**Created**: 2026-08-07

**Status**: Draft

**Input**: User description: "Arranquemos con la especificacion de la epica H3.3 - Feedback y aprendizaje controlado del backlog, con alcance exacto UM-H3-023 a UM-H3-031."

## Clarifications

### Session 2026-08-07

- Q: ¿Que criterio define que las señales de feedback son "suficientes" para
  proponer aprendizaje (UM-H3-028)? → A: Politica de aprendizaje versionada y
  determinista: un minimo de señales estructuradas consistentes (mismo
  concepto, misma polaridad) dentro de una ventana, con confianza minima de
  señal, cooldown para no re-proponer el mismo cambio y expiracion de
  propuestas pendientes. Los umbrales viven en una version inmutable y
  consultable (patron de la scoring policy de H3.2); sin LLM en el camino
  critico.
- Q: ¿Que rol cumple el feedback libre contextual (UM-H3-027, P1) en el
  aprendizaje? → A: Solo insumo cualitativo para investigacion de producto:
  se guarda con contexto (busqueda y listing), la UI explica como se usara y
  0 contenido de texto llega a analytics; no se parsea ni se vincula a
  propuestas de aprendizaje en v1.
- Q: ¿Que acciones de feedback cuentan como señales de aprendizaje y es
  obligatoria una razon rapida? → A: Solo like y dislike con razones rapidas
  cuentan como señales para propuestas. Save, dismiss y contacted registran
  estado y evidencia (feedback events) pero 0 generan propuestas por si
  solos.
- Q: ¿Como descubre el usuario una propuesta de aprendizaje pendiente? → A:
  Aviso inline en la vista del radar (banner/tarjeta visible al abrir) con
  acciones de confirmar, ampliar o descartar y enlace al detalle de la
  propuesta. Sin notificaciones externas en este incremento (push/email son
  H5).

## Operational Definitions

- **Feedback event**: registro inmutable y append-only de una accion de
  decision de un usuario sobre un listing dentro de una busqueda: tipo (like,
  dislike, save, dismiss, contacted), razones rapidas opcionales, feedback
  libre opcional (P1), actor, contexto (busqueda, recommendation item y run
  cuando aplique), clave de idempotencia y timestamp. Ningun evento se muta:
  un cambio de decision crea un evento nuevo con referencia de compensacion al
  evento que supera.
- **Estado de decision actual**: estado derivado (save, dismiss, like,
  dislike, contacted o ninguno) por (busqueda, listing), calculado siempre del
  ultimo evento vigente de la cadena de compensacion; nunca se muta el
  historial para cambiar el estado.
- **Razon rapida**: categoria curada y versionada de motivo (precio,
  expensas, ubicacion, ambientes, superficie, estado del edificio,
  transporte/accesibilidad, otro) con referencia opcional al concepto del
  concept registry (H3.1); se ofrece como opciones de un toque en card y
  detalle.
- **Feedback libre**: texto opcional del usuario que explica un like o
  dislike, capturado con contexto y limite de longitud; es solo insumo
  cualitativo para investigacion, no se parsea ni se vincula a propuestas de
  aprendizaje en v1 y se evita PII en analytics.
- **Senal de aprendizaje**: evento estructurado de like o dislike con razones
  rapidas (concepto y polaridad) que cuenta como evidencia para una propuesta
  de aprendizaje, dentro del alcance de su busqueda. Save, dismiss y contacted
  registran estado y evidencia pero 0 generan propuestas por si solos.
- **Propuesta de aprendizaje**: cambio sugerido (preference fact o criterio
  ejecutable) derivado de señales suficientes, con evidencia (refs a feedback
  events), alcance por busqueda, efecto esperado y estado (pendiente,
  confirmada, rechazada, expirada, superada). Nada se aplica sin confirmacion
  explicita del usuario.
- **Confirmacion de aprendizaje**: accion explicita del usuario que convierte
  una propuesta en preference fact o criterio versionado a traves de la
  compilacion de H3.1, versiona el perfil de busqueda y dispara un nuevo run
  (UM-H3-030). Deshacer revierte el cambio con compensacion trazable.
- **Ampliar aprendizaje**: editar la propuesta (valor, peso, alcance o
  razones) antes de confirmarla; el usuario ve el cambio exacto y su efecto
  esperado.
- **Recalculado tras cambios relevantes**: nueva ejecucion atomica de scoring
  (maquinaria de runs de H3.2) disparada por cambios confirmados de criterios;
  el run anterior queda congelado y consultable para auditoria.
- **Historial de cambios del listing**: secuencia de cambios confirmados de
  precio y atributos con fechas y fuente, derivada de las listing versions de
  H2.2; no se infieren tendencias con muestra insuficiente.

## Review and Measurement Protocol

- La puerta de salida del hito: cada recomendacion se reconstruye desde
  perfil, listing, features, scoring y evidencia; todo feedback persiste como
  evento. Este incremento entrega feedback inmutable e idempotente, vistas de
  shortlist/descartados, propuestas de aprendizaje con confirmacion y
  recalculado. El dataset golden y las regresiones (H3.4), el chat (H4) y las
  notificaciones (H5) NO se evaluan aqui.
- Los feedback events se verifican confirmando que el 100% persiste actor,
  contexto, referencia al recommendation item/listing y timestamp, y que 0
  eventos se mutan: el historial completo es consultable y append-only.
- La idempotencia se verifica repitiendo la misma accion con la misma clave y
  con claves distintas: repetir no duplica eventos y el estado actual es unico
  por (busqueda, listing) derivado del ultimo evento vigente.
- Los cambios de decision se verifican con la secuencia like -> dislike ->
  like: cada cambio genera un evento nuevo con compensacion trazable, el
  estado final coincide con el ultimo evento y el historial conserva todos los
  pasos.
- La superficie de feedback se verifica con tests de componente y revision de
  accesibilidad/copy por convencion del proyecto: card y detalle ofrecen
  guardar, descartar, like/dislike y razones rapidas, con confirmacion visible
  y estados optimistas reversibles; el undo no esta disponible para contacted
  (terminal).
- Las vistas de shortlist y descartados se verifican confirmando que persisten
  por busqueda, sobreviven recarga y navegacion, ofrecen filtros por estado y
  retorno al detalle, y que los descartados quedan ocultos del radar por
  defecto con opcion de mostrarlos.
- Las propuestas de aprendizaje se verifican con casos golden de senales
  (suficientes e insuficientes segun la politica definida por clarificacion):
  el 100% de las propuestas registra evidencia, alcance por busqueda, efecto
  esperado y estado; 0 propuestas se aplican sin confirmacion, 0 cambios
  globales automaticos ocurren y 0 propuestas derivan de save, dismiss o
  contacted.
- La confirmacion, deshacer y ampliacion se verifican ejecutando los tres
  flujos: confirmar versiona el perfil y crea un run nuevo; deshacer revierte
  con compensacion trazable y crea su run; ampliar permite editar antes de
  confirmar. En el 100% de los casos el usuario ve el cambio exacto, el
  alcance y el efecto esperado, y el 100% de las propuestas pendientes es
  descubrible via aviso inline en el radar sin notificaciones externas.
- El recalculado se verifica confirmando que solo los cambios confirmados de
  criterios (o ediciones explicitas de perfil) crean runs nuevos, que el run
  anterior queda consultable y que el feedback directo sin aprendizaje
  confirmado 0 genera runs nuevos (solo estado y vistas).
- El feedback libre (P1) se verifica confirmando que es opcional, con limite
  de longitud y contexto, y que 0 contenido de texto llega a analytics.
- El historial de precio y cambios (P1) se verifica confirmando que el 100%
  de los cambios mostrados tiene fecha y fuente confirmadas y que 0
  superficies infieren tendencias con muestra insuficiente.
- La instrumentacion se verifica confirmando que feedback, propuestas,
  confirmaciones y vistas emiten sus eventos versionados sin PII innecesaria,
  de acuerdo con UM-H0-013, habilitando la precision percibida de UM-H0-014 en
  H6.
- Los contratos HTTP se verifican con errores tipados y deny-by-default: el
  feedback de una busqueda o usuario ajeno se deniega sin filtrar datos.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Expresar opinion en card y detalle con feedback inmutable (Priority: P0)

Como usuario del radar, quiero guardar, descartar, dar like/dislike y elegir
razones rapidas desde la card o el detalle, con confirmacion visible y la
posibilidad de deshacer, para que cada decision que tomo quede registrada de
forma confiable y se refleje de inmediato.

**Why this priority**: Es el corazon de H3.3: sin feedback persistente,
inmutable e idempotente no hay precision percibida, aprendizaje ni cierre de
loop; ademas habilita la metrica principal de beta.

**Independent Test**: El conjunto de prueba registra las cinco acciones desde
card y detalle, repite la misma accion y verifica que el estado actual es
unico y el historial no se duplica ni se muta.

**Acceptance Scenarios**:

1. **Given** una card o detalle de un listing del radar, **When** el usuario
   guarda, descarta, da like, da dislike o marca contacted, **Then** se
   persiste un feedback event inmutable con actor, contexto, referencia al
   recommendation item y timestamp, y la UI confirma la accion visiblemente.
2. **Given** la misma accion repetida con la misma clave de idempotencia,
   **When** se registra, **Then** no se duplica ningun evento y el estado
   queda igual.
3. **Given** una accion ya vigente (por ejemplo, guardar un listing ya
   guardado), **When** se repite, **Then** es un no-op idempotente: 0 eventos
   duplicados.
4. **Given** una secuencia like -> dislike -> like, **When** cada cambio se
   registra, **Then** cada uno genera un evento nuevo con compensacion
   trazable al superado, el estado final es el del ultimo evento y el
   historial conserva los tres pasos.
5. **Given** un listing con reasons rapidas, **When** el usuario elige una
   razon, **Then** queda vinculada al evento con referencia opcional al
   concepto del registry.
6. **Given** un listing descartado o guardado por error, **When** el usuario
   deshace, **Then** el estado se revierte con un evento de compensacion
   trazable; contacted no ofrece undo (terminal).

---

### User Story 2 - Shortlist y descartados persistentes (Priority: P0)

Como usuario del radar, quiero ver mis listings guardados y descartados en
vistas persistentes por busqueda, con filtros y retorno al detalle, para
retomar decisiones con contexto sin perder el historial.

**Why this priority**: Da superficie de producto a los estados de decision y
reutiliza la shortlist persistida en H3.2; completa el recorrido de
exploracion del radar.

**Independent Test**: El conjunto de prueba guarda y descarta listings, recarga
la aplicacion y verifica que las vistas persisten por busqueda, filtran por
estado y navegan al detalle.

**Acceptance Scenarios**:

1. **Given** listings guardados y descartados en una busqueda, **When** se
   abre la vista correspondiente, **Then** se muestran persistidos por
   busqueda y sobreviven recarga y navegacion.
2. **Given** la vista de shortlist o descartados, **When** el usuario filtra
   por estado o razon, **Then** los resultados se filtran sin perder el
   contexto de la busqueda.
3. **Given** un item de la vista, **When** el usuario navega, **Then** llega
   al detalle del listing con su explicacion y feedback actuales.
4. **Given** un listing descartado, **When** se muestra el radar por defecto,
   **Then** queda oculto con opcion de mostrarlo; guardar un listing
   descartado revierte el estado al del ultimo evento.
5. **Given** una busqueda ajena, **When** se consultan sus vistas, **Then** se
   deniega con deny-by-default sin filtrar datos.

---

### User Story 3 - Proponer aprendizaje desde señales de feedback (Priority: P0)

Como sistema de matching, quiero convertir señales de feedback suficientes en
una propuesta de preference fact o criterio por busqueda, con evidencia y sin
aplicar cambios automaticos, para aprender sin romper el control del usuario.

**Why this priority**: Es el aprendizaje controlado del hito: convierte
opiniones repetidas en cambios de criterio auditables, respetando que el
ranking final no lo decida una respuesta generativa y que nada cambie sin
confirmacion.

**Independent Test**: El conjunto de prueba alimenta senales suficientes e
insuficientes y verifica que la propuesta se genera solo cuando corresponde,
con evidencia, alcance y estado; 0 propuestas se aplican solas.

**Acceptance Scenarios**:

1. **Given** al menos el minimo de senales estructuradas consistentes sobre un
   mismo concepto (misma polaridad) dentro de la ventana definida por la
   politica de aprendizaje versionada, **When** se evalua el aprendizaje,
   **Then** se crea una propuesta con evidencia (refs a feedback events),
   alcance por busqueda, efecto esperado y estado pendiente.
2. **Given** senales insuficientes o contradictorias, **When** se evalua,
   **Then** 0 propuestas se generan.
3. **Given** una propuesta pendiente, **When** llegan nuevas senales que la
   contradicen, **Then** la propuesta se supera o ajusta con trazabilidad; 0
   propuestas duplicadas sobre el mismo cambio dentro del cooldown.
4. **Given** una propuesta, **When** el usuario aun no decide, **Then** queda
   pendiente hasta confirmarse, rechazarse o expirar; 0 cambios se aplican sin
   confirmacion explicita.
5. **Given** una propuesta que escalaria a hard filter, **When** se presenta,
   **Then** requiere confirmacion explicita del usuario y nunca se aplica de
   forma automatica.
6. **Given** acciones de save, dismiss o contacted (con o sin razones), **When**
   se evalua el aprendizaje, **Then** 0 propuestas se generan; esas acciones
   solo registran estado y evidencia.

---

### User Story 4 - Confirmar, deshacer o ampliar aprendizaje (Priority: P0)

Como usuario del radar, quiero ver el cambio exacto que el sistema propone,
su alcance y su efecto esperado, y poder confirmarlo, deshacerlo o ampliarlo,
para que el radar aprenda solo lo que yo decida.

**Why this priority**: Sin confirmacion visible el aprendizaje seria opaco y
violaria el principio de matching auditable; la confianza depende de que el
cambio sea explicito y reversible.

**Independent Test**: El conjunto de prueba ejecuta los tres flujos
(confirmar, deshacer, ampliar) y verifica el diff mostrado, el versionado del
perfil y la creacion de runs en cada caso.

**Acceptance Scenarios**:

1. **Given** una propuesta pendiente, **When** el usuario confirma, **Then**
   se aplica como preference fact o criterio versionado via la compilacion de
   H3.1, se versiona el perfil y se crea un run nuevo.
2. **Given** una propuesta, **When** se muestra, **Then** el usuario ve el
   cambio exacto (diff), el alcance de busqueda y el efecto esperado antes de
   decidir.
3. **Given** una propuesta, **When** el usuario la amplia, **Then** puede
   editar valor, peso o alcance antes de confirmarla y el diff se actualiza.
4. **Given** un cambio confirmado, **When** el usuario lo deshace, **Then** se
   revierte con compensacion trazable (fact superado, perfil versionado, run
   nuevo) y el run anterior queda consultable.
5. **Given** una propuesta expirada o superada, **When** el usuario intenta
   confirmarla, **Then** la accion se rechaza con error accionable y 0 cambios
   se aplican.
6. **Given** una propuesta pendiente, **When** se abre la vista del radar,
   **Then** aparece un aviso inline (banner/tarjeta) con acciones de
   confirmar, ampliar o descartar y enlace al detalle; 0 notificaciones
   externas en este incremento (H5).

---

### User Story 5 - Recalcular tras cambios relevantes (Priority: P0)

Como sistema, quiero que cada cambio confirmado de criterios versione el
perfil, cree un run nuevo con la maquinaria de H3.2 y conserve el run anterior
para auditoria, para que el radar refleje las preferencias aprendidas sin
perder trazabilidad.

**Why this priority**: Cierra el loop de H3.3: el aprendizaje confirmado debe
traducirse en resultados nuevos, atomicos y auditables, sin invalidar la
historia.

**Independent Test**: El conjunto de prueba confirma un aprendizaje y verifica
que se versiona el perfil, se publica un run nuevo atomico y el run anterior
sigue consultable; el feedback directo 0 genera runs nuevos.

**Acceptance Scenarios**:

1. **Given** un aprendizaje confirmado, **When** se aplica, **Then** se
   versiona el perfil, se crea un run nuevo con profile snapshot y policy
   versionados y el run anterior queda congelado y consultable.
2. **Given** feedback directo (like, dislike, save, dismiss) sin aprendizaje
   confirmado, **When** el usuario lo registra, **Then** 0 runs nuevos se
   crean: solo cambian el estado y las vistas.
3. **Given** un run nuevo tras aprendizaje, **When** falla a mitad, **Then**
   el ultimo run valido permanece publicado y el fallo registra su causa (regla
   de H3.2).
4. **Given** el radar tras el recalculado, **When** se consultan explicaciones,
   **Then** corresponden al run vigente con su profile snapshot, sin mezclar
   versiones.

---

### User Story 6 - Capturar feedback libre contextual (Priority: P1)

Como usuario del radar, quiero poder explicar un like o dislike con texto
libre opcional, sin obligacion de escribir, entendiendo como se usara y sin
que ese texto termine en analytics, para aportar matices que las razones
rapidas no cubren.

**Why this priority**: Es P1 del backlog: enriquece el aprendizaje cualitativo
y la investigacion, pero no bloquea el camino critico de la beta.

**Independent Test**: El conjunto de prueba captura feedback libre opcional
con contexto y verifica el aviso de uso, el limite de longitud y 0 PII en
analytics.

**Acceptance Scenarios**:

1. **Given** un like o dislike, **When** el usuario agrega feedback libre,
   **Then** queda opcional, con limite de longitud y contexto de busqueda y
   listing.
2. **Given** la superficie de feedback libre, **When** se muestra, **Then**
   explica como se usara el texto (insumo cualitativo para investigacion) y
   que no se comparte ni genera cambios automaticos.
3. **Given** un texto libre capturado, **When** se instrumenta, **Then** 0
   contenido de texto se incluye en analytics o eventos de producto.
4. **Given** un like o dislike sin texto, **When** se registra, **Then** el
   evento es igualmente valido (el texto es opcional).

---

### User Story 7 - Mostrar historial de precio y cambios (Priority: P1)

Como usuario del radar, quiero ver los cambios confirmados de precio y
atributos de un listing con sus fechas y fuente, sin que el sistema infiera
tendencias con muestra insuficiente, para evaluar estabilidad con datos reales.

**Why this priority**: Es P1 del backlog: completa la confianza en el detalle
con datos de listing versions (H2.2), sin caer en afirmaciones no soportadas.

**Independent Test**: El conjunto de prueba revisa el historial de listings con
cambios y verifica fechas, fuente y ausencia de inferencias de tendencia.

**Acceptance Scenarios**:

1. **Given** un listing con cambios confirmados de precio o atributos, **When**
   se muestra el historial, **Then** cada cambio aparece con fecha, fuente y
   valor before/after.
2. **Given** un listing sin cambios o con muestra insuficiente, **When** se
   muestra, **Then** se declara que no hay suficiente historial y 0 tendencias
   se infieren.
3. **Given** el historial, **When** se navega, **Then** enlaza al detalle y a
   la explicacion vigente sin mezclar versiones de runs.

### Edge Cases

- Repetir la misma accion con la misma clave de idempotencia 0 duplica
  eventos; repetir una accion ya vigente es un no-op.
- Cambiar de decision genera un evento nuevo con compensacion trazable; el
  estado actual siempre deriva del ultimo evento vigente y es unico por
  (busqueda, listing).
- Contacted es terminal: 0 undo; save, dismiss, like y dislike son
  reversibles.
- Guardar un listing descartado revierte el estado al del ultimo evento: el
  listing vuelve a la vista por defecto y a la shortlist.
- Un listing sin run publicado (legacy del baseline de H2.3) acepta feedback
  con contexto de listing; las explicaciones legacy siguen sin desglose y 0
  razones se fabrican.
- Las senales insuficientes o contradictorias 0 generan propuestas; una
  propuesta superada por nueva evidencia queda con estado superado y trazable.
- Solo like/dislike con razones rapidas generan propuestas; save, dismiss y
  contacted 0 generan propuestas por si solos (solo estado y evidencia).
- Confirmar una propuesta expirada o superada se rechaza con error accionable.
- Las propuestas pendientes se descubren con un aviso inline en el radar; 0
  notificaciones externas en este incremento (H5).
- Deshacer un aprendizaje confirmado revierte con compensacion trazable y
  crea un run nuevo; el run intermedio queda consultable.
- El feedback directo sin aprendizaje confirmado 0 crea runs nuevos: solo
  cambia estado y vistas.
- Un run nuevo fallido a mitad no reemplaza al ultimo valido y registra la
  causa (regla de H3.2).
- El feedback libre 0 llega a analytics; 0 PII se emite en eventos.
- El historial de cambios 0 infiere tendencias con muestra insuficiente y solo
  muestra cambios confirmados con fecha y fuente.
- 0 superficies acceden a feedback de otras busquedas u otros usuarios;
  deny-by-default en contratos.
- 0 cambios globales automaticos: el aprendizaje se propone y confirma por
  busqueda; la memoria global de multiples radares es R4-003.

## Requirements *(mandatory)*

### Functional Requirements

#### Feedback events inmutables

- **FR-001**: El sistema MUST soportar feedback events de tipo like, dislike,
  save, dismiss y contacted, con razones rapidas opcionales y feedback libre
  opcional (P1); cada evento MUST conservar actor, contexto de busqueda,
  referencia al recommendation item (o al listing cuando no exista item) y
  timestamp.
- **FR-002**: Los feedback events MUST ser inmutables y append-only: 0
  mutaciones sobre eventos registrados y el historial completo MUST quedar
  consultable.

#### Idempotencia y cambios de decision

- **FR-003**: Registrar la misma accion con la misma clave de idempotencia
  MUST NO duplicar eventos; repetir una accion cuyo estado resultante ya esta
  vigente MUST ser un no-op idempotente.
- **FR-004**: Un cambio de decision (por ejemplo, like -> dislike) MUST
  generar un evento nuevo con compensacion trazable al evento superado; el
  estado de decision actual por (busqueda, listing) MUST derivar del ultimo
  evento vigente y ser unico.

#### Superficie de feedback

- **FR-005**: Card y detalle MUST ofrecer guardar, descartar, like/dislike y
  razones rapidas, accesibles por teclado y lectores de pantalla, con
  confirmacion visible y estados optimistas reversibles; contacted MUST ser
  terminal (sin undo) y save/dismiss/like/dislike MUST ser reversibles.
- **FR-006**: Las razones rapidas MUST ser categorias curadas y versionadas,
  opcionales, con referencia opcional al concepto del concept registry (H3.1).

#### Shortlist y descartados

- **FR-007**: Las vistas de shortlist y descartados MUST persistir por
  busqueda (reutilizando la shortlist de H3.2), sobrevivir recarga y
  navegacion, ofrecer filtros por estado/razon y retorno al detalle.
- **FR-008**: Un listing descartado MUST quedar oculto del radar por defecto
  con opcion de mostrarlo; guardar un listing descartado MUST revertir el
  estado al del ultimo evento.

#### Propuestas de aprendizaje

- **FR-009**: El sistema MUST convertir senales de feedback suficientes en
  propuestas de preference fact o criterio ejecutable por busqueda, con
  evidencia (refs a feedback events), efecto esperado y estado (pendiente,
  confirmada, rechazada, expirada, superada). La suficiencia MUST regirse por
  una politica de aprendizaje versionada e inmutable que fije el minimo de
  senales consistentes (mismo concepto, misma polaridad) dentro de una
  ventana, la confianza minima de señal, el cooldown para no re-proponer el
  mismo cambio y la expiracion de propuestas pendientes; cada cambio de
  politica MUST producir una version nueva sin modificar versiones previas y 0
  LLM MUST intervenir en la decision. Solo los eventos de like y dislike con
  razones rapidas MUST contar como senales; save, dismiss y contacted MUST
  registrar estado y evidencia pero MUST NO generar propuestas por si solos.
- **FR-010**: 0 propuestas MUST aplicarse sin confirmacion explicita del
  usuario; 0 cambios globales automaticos; 0 escalamiento a hard filter sin
  confirmacion explicita.
- **FR-011**: Las propuestas MUST deduplicarse sobre el mismo cambio dentro
  del cooldown definido, superarse con trazabilidad ante nueva evidencia
  contradictoria y expirar si no se deciden en la ventana definida.

#### Confirmacion, deshacer y ampliacion

- **FR-012**: Confirmar una propuesta MUST aplicarla como preference fact o
  criterio versionado via la compilacion de H3.1, versionar el perfil y
  disparar un run nuevo; deshacer MUST revertir con compensacion trazable;
  ampliar MUST permitir editar valor, peso o alcance antes de confirmar.
- **FR-013**: Antes de decidir, el usuario MUST ver el cambio exacto (diff),
  el alcance de busqueda y el efecto esperado; confirmar una propuesta
  expirada o superada MUST rechazarse con error accionable. Las propuestas
  pendientes MUST descubrirse con un aviso inline en la vista del radar
  (banner/tarjeta) con acciones de confirmar, ampliar o descartar y enlace al
  detalle; 0 notificaciones externas en este incremento (H5).

#### Recalculado tras cambios relevantes

- **FR-014**: Los cambios confirmados de criterios (o ediciones explicitas de
  perfil) MUST versionar el perfil y crear un run nuevo atomico con la
  maquinaria de H3.2; el run anterior MUST quedar congelado y consultable.
- **FR-015**: El feedback directo sin aprendizaje confirmado MUST NO crear
  runs nuevos: solo MUST actualizar el estado de decision y las vistas.

#### Feedback libre (P1)

- **FR-016**: El feedback libre MUST ser opcional (el like/dislike sin texto es
  valido), con limite de longitud y contexto de busqueda y listing; la
  superficie MUST explicar como se usara el texto. El feedback libre MUST ser
  solo insumo cualitativo para investigacion: 0 parseo automatico y 0
  vinculacion a propuestas de aprendizaje en v1, y 0 contenido de texto MUST
  llegar a analytics.

#### Historial de cambios (P1)

- **FR-017**: El historial de precio y atributos MUST mostrar solo cambios
  confirmados con fecha y fuente (listing versions de H2.2) y MUST NO inferir
  tendencias con muestra insuficiente.

#### Transversal

- **FR-018**: Feedback, propuestas, confirmaciones y vistas MUST emitir
  eventos versionados de auditoria/telemetria sin PII innecesaria, de acuerdo
  con UM-H0-013, habilitando la medicion de precision percibida de
  UM-H0-014.
- **FR-019**: Los contratos HTTP de feedback, shortlist, descartados y
  aprendizaje MUST respetar ownership con deny-by-default y errores tipados;
  accesos a busquedas o usuarios ajenos MUST denegarse sin filtrar datos.
- **FR-020**: Las superficies nuevas MUST ser operables por teclado y
  accesibles (nombres y contraste acordados), de acuerdo con el DoD del
  proyecto.
- **FR-021**: El incremento MUST exponer los contratos HTTP necesarios para la
  superficie web de H3.3 y MUST NO exponer consola operativa de feedback ni de
  aprendizaje (H6).

### Key Entities

- **Feedback Event**: registro inmutable y append-only de una accion de
  decision (like, dislike, save, dismiss, contacted) con actor, contexto,
  referencia al item/listing, razones y feedback libre opcional.
- **Decision State**: estado derivado por (busqueda, listing) del ultimo
  evento vigente de la cadena de compensacion.
- **Quick Reason**: categoria curada y versionada de motivo con referencia
  opcional al concepto del registry.
- **Free Feedback**: texto opcional contextual de un like/dislike, sin PII en
  analytics.
- **Learning Signal**: evento estructurado que cuenta como evidencia para
  propuestas dentro del alcance de su busqueda.
- **Learning Proposal**: cambio sugerido (preference fact o criterio) con
  evidencia, alcance por busqueda, efecto esperado y estado; 0 aplicacion sin
  confirmacion.
- **Preference Fact**: hecho de preferencia versionado (H3.1) que materializa
  un aprendizaje confirmado.
- **Profile Version / Recommendation Run**: perfil versionado y run atomico
  (H3.2) creados tras cambios confirmados; el run anterior queda consultable.
- **Listing Change History**: cambios confirmados de precio y atributos con
  fecha y fuente (H2.2), sin inferencias de tendencia.
- **Product Event**: registro versionado de feedback, aprendizaje y vistas sin
  PII innecesaria.

### Backlog Traceability

| User Story | Backlog scope |
| --- | --- |
| User Story 1 - Feedback inmutable en card/detalle | UM-H3-023, UM-H3-024, UM-H3-025 |
| User Story 2 - Shortlist y descartados | UM-H3-026 |
| User Story 3 - Propuestas de aprendizaje | UM-H3-028 |
| User Story 4 - Confirmar, deshacer o ampliar | UM-H3-029 |
| User Story 5 - Recalcular tras cambios | UM-H3-030 |
| User Story 6 - Feedback libre contextual | UM-H3-027 |
| User Story 7 - Historial de precio y cambios | UM-H3-031 |

### Requirement Traceability

| Backlog item | Functional requirements | Acceptance evidence |
| --- | --- | --- |
| UM-H3-023 | FR-001, FR-002, FR-018 | US1.1, US1.5, SC-001, SC-008 |
| UM-H3-024 | FR-003, FR-004 | US1.2-US1.4, SC-002 |
| UM-H3-025 | FR-005, FR-006 | US1.5-US1.6, SC-003 |
| UM-H3-026 | FR-007, FR-008, FR-019 | US2.1-US2.5, SC-004 |
| UM-H3-027 | FR-016, FR-018 | US6.1-US6.4, SC-006 |
| UM-H3-028 | FR-009, FR-010, FR-011 | US3.1-US3.5, SC-005 |
| UM-H3-029 | FR-012, FR-013 | US4.1-US4.5, SC-005, SC-006 |
| UM-H3-030 | FR-014, FR-015 | US5.1-US5.4, SC-007 |
| UM-H3-031 | FR-017 | US7.1-US7.3, SC-009 |
| Transversal (todos) | FR-018, FR-019, FR-020, FR-021 | SC-008, SC-010 |

## Constitution Alignment *(mandatory)*

- **Persistent product objects**: feedback events, estados de decision,
  propuestas y aprendizajes confirmados son objetos persistentes y versionados
  vinculados a su busqueda; ninguna decision del usuario vive solo en una
  respuesta efimera. Sustenta el principio I (radar como fuente de verdad) y
  UM-H3-023.
- **Auditable deterministic matching**: el aprendizaje se propone con reglas
  deterministas sobre senales estructuradas y 0 propuestas se aplican sin
  confirmacion; el ranking final sigue siendo decisión del scoring puro de
  H3.2. Sustenta el principio II y el patron prohibido de "ranking generativo".
- **Data lineage, observability and trust**: cada propuesta referencia sus
  feedback events (evidencia interna), cada cambio confirmado versiona perfil y
  run conservando el anterior, cada decision registra compensacion trazable y
  los eventos no llevan PII innecesaria. Sustenta el principio V y el guardrail
  de recomendaciones con lineage completo.
- **Versioned prompts, models and schemas**: este incremento no incorpora
  parseo generativo del feedback libre: las propuestas derivan de senales
  estructuradas y razones curadas; si un incremento posterior incorporara
  analisis de texto, deberia versionar modelo/prompt/schema y no agregar
  hechos.
- **Verification approach**: casos golden de idempotencia, secuencias de
  cambio de decision, senales suficientes/insuficientes, flujos de
  confirmacion/deshacer/ampliacion, recalculado con fallo inducido y revision
  de copy/accesibilidad de la web.
- **Dependency direction**: feedback, propuestas y aprendizaje son
  dominio/aplicacion puros que consumen la compilacion de H3.1 y la maquinaria
  de runs de H3.2; la web consume contratos de Product API con permisos
  deny-by-default.
- **Minimal change**: el incremento se limita a UM-H3-023 a UM-H3-031 y excluye
  dataset golden y regresiones (H3.4), chat (H4) y notificaciones (H5). El
  feedback libre y el historial de cambios son P1.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: El 100% de las acciones de feedback persiste un evento inmutable
  con actor, contexto, referencia al item/listing y timestamp; 0 eventos se
  mutan y 0 acciones repetidas con la misma clave duplican eventos.
- **SC-002**: El 100% de las secuencias de cambio de decision del conjunto de
  prueba genera eventos con compensacion trazable; 0 estados ambiguos y el
  estado actual coincide con el ultimo evento vigente en el 100% de los casos.
- **SC-003**: El 100% de las superficies de feedback revisadas (card y
  detalle) ofrece guardar, descartar, like/dislike y razones rapidas
  accesibles, con confirmacion visible y undo operativo (excepto contacted);
  el 100% de los fallos de red revierte el estado optimista.
- **SC-004**: El 100% de las vistas de shortlist y descartados persiste por
  busqueda y sobrevive recarga; los descartados quedan ocultos del radar por
  defecto con opcion de mostrarlos; 0 accesos cruzados entre busquedas o
  usuarios devuelven datos.
- **SC-005**: El 100% de las propuestas generadas cumple el criterio de
  suficiencia definido, registra evidencia, alcance y efecto esperado; 0
  propuestas se aplican sin confirmacion, 0 cambios globales automaticos
  ocurren y 0 propuestas derivan de save, dismiss o contacted; 0 propuestas
  duplicadas dentro del cooldown.
- **SC-006**: El 100% de los flujos confirmar/deshacer/ampliar muestra el
  cambio exacto, el alcance y el efecto esperado; el 100% de las
  confirmaciones versiona el perfil y crea un run nuevo, y el 100% de los
  deshaceres revierte con compensacion trazable. El 100% de las propuestas
  pendientes es descubrible via aviso inline en el radar.
- **SC-007**: El 100% de los cambios confirmados de criterios crea un run
  nuevo atomico conservando el anterior consultable; 0 feedback directo sin
  aprendizaje confirmado genera runs nuevos.
- **SC-008**: El 100% de los eventos de feedback, propuestas y vistas se emite
  versionado y sin PII innecesaria; 0 contenido de feedback libre llega a
  analytics.
- **SC-009** (P1): El 100% de los cambios mostrados en el historial tiene
  fecha y fuente confirmadas; 0 superficies infieren tendencias con muestra
  insuficiente.
- **SC-010**: El 100% de los contratos HTTP del incremento respeta ownership
  con deny-by-default y errores tipados; las superficies nuevas cumplen la
  revision de accesibilidad y copy por convencion del proyecto.

## Assumptions

- El alcance incluye exactamente UM-H3-023 a UM-H3-031 (Epica H3.3 - Feedback
  y aprendizaje controlado). El dataset golden y las regresiones de scoring
  (H3.4), el chat (H4) y las alertas (H5) quedan fuera y se especifican en sus
  propios incrementos.
- Depende de H3.1 (concept registry, preference facts, compilacion de
  criterios) y H3.2 (scoring policy, runs atomicos, shortlist persistida de
  UM-H3-022): este incremento consume esa maquinaria y no la reimplementa. Las
  vistas de producto de shortlist/descartados de H3.3 usan la misma
  persistencia de shortlist de H3.2.
- Los estados de decision derivan del ultimo evento vigente: dismiss oculta
  del radar por defecto (filtrable), save agrega a la shortlist; save, dismiss,
  like y dislike son reversibles con eventos de compensacion; contacted es
  terminal. Repetir una accion ya vigente es un no-op idempotente.
- Las razones rapidas parten de un set curado inicial (precio, expensas,
  ubicacion, ambientes, superficie, estado del edificio, transporte/
  accesibilidad, otro) con referencia opcional a conceptos del registry; el
  set exacto se afina en el plan sin cambiar el alcance.
- La politica de aprendizaje (UM-H3-028) es versionada e inmutable (decision
  de clarificacion 2026-08-07): fija el minimo de senales consistentes (mismo
  concepto, misma polaridad) dentro de una ventana, la confianza minima de
  señal, el cooldown para no re-proponer el mismo cambio y la expiracion de
  propuestas pendientes; sin LLM en el camino critico. Los valores exactos se
  definen en el plan y los contratos, sin cambiar el alcance.
- El feedback libre (UM-H3-027) es solo insumo cualitativo para investigacion
  (decision de clarificacion 2026-08-07): se guarda con contexto, la UI
  explica su uso, 0 contenido llega a analytics y no se parsea ni se vincula a
  propuestas de aprendizaje en v1.
- Solo los like y dislike con razones rapidas cuentan como senales de
  aprendizaje (decision de clarificacion 2026-08-07); save, dismiss y
  contacted registran estado y evidencia pero 0 generan propuestas por si
  solos.
- Las propuestas pendientes se descubren con un aviso inline en la vista del
  radar (banner/tarjeta) con acciones de confirmar, ampliar o descartar
  (decision de clarificacion 2026-08-07); las notificaciones externas
  (push/email) son H5 y quedan fuera.
- Las propuestas de aprendizaje se aplican exclusivamente por confirmacion
  explicita y por busqueda; la memoria global de preferencias (multiples
  radares) es R4-003 y queda fuera. Un escalamiento a hard filter requiere
  confirmacion explicita adicional segun la regla de H3.1.
- El recalculado (UM-H3-030) se dispara por cambios confirmados de criterios y
  por ediciones explicitas de perfil (triggers existentes de H2.3/H3.2); el
  feedback directo sin aprendizaje confirmado no crea runs nuevos, solo
  actualiza estado y vistas.
- Los listings sin run publicado con desglose (legacy del baseline de H2.3)
  aceptan feedback con contexto de listing; las explicaciones legacy siguen
  sin desglose y 0 razones se fabrican.
- El historial de cambios (UM-H3-031) muestra solo cambios confirmados con
  fecha y fuente desde listing versions (H2.2); 0 inferencias de tendencia en
  v1.
- La precision percibida (UM-H0-014) se calcula en H6: este incremento solo
  emite los eventos versionados que la habilitan (save/like/contacted dentro
  de la ventana).
- Los contratos HTTP de feedback, shortlist, descartados y aprendizaje se
  exponen en este incremento (las stories WEB UM-H3-025, UM-H3-026, UM-H3-027,
  UM-H3-029 y UM-H3-031 requieren contratos); no se expone consola operativa
  de feedback ni de aprendizaje (H6).
- El idioma de los casos golden y del copy de la web es espanol (CABA), sobre
  el dataset controlado.
- La verificacion de idempotencia, trazabilidad, aprendizaje y recalculado se
  ejecuta sobre el conjunto de prueba del harness con casos golden, de acuerdo
  con el DoD del proyecto; la superficie web se verifica con tests de
  componente y revision de accesibilidad/copy por convencion del proyecto.
