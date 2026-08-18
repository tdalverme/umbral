# Research: Copiloto conversacional de búsqueda

## Decisión 1 — Separar la verdad del usuario de las capacidades del producto

**Decisión**: introducir `PreferenceExpression` y `CriterionBinding` como un módulo de aplicación nuevo (`umbral.application.preferences`). La expresión conserva el deseo completo por radar. La vinculación declara si ese deseo puede traducirse a un concepto estructurado, a similitud semántica suave o a un estado no evaluable/prohibido. `PreferenceFact` y `CompiledCriterion` siguen siendo la parte computable.

**Razón**: el número de filas puede crecer con los usuarios, pero el esquema y el catálogo de conceptos permanecen finitos. Esto evita crear una columna, clase o concepto compartido para “cocina grande”, “cafés para trabajar” o cualquier formulación individual.

**Alternativas descartadas**:

- Agregar un concepto global por frase: convierte ruido individual en deuda de catálogo y extracción.
- Guardar solo texto libre en el chat: pierde estado durable, corrección y trazabilidad.
- Convertir toda frase en embedding: confunde memoria con evidencia y permite que una señal débil influya demasiado.

## Decisión 2 — Un radar parcial es un radar activo, no un borrador separado

**Decisión**: `zones=()` significa alcance abierto dentro de CABA; `budget_max=None` y `min_rooms=None` significan “sin restricción declarada”. No se agrega un estado `draft`. La operación continúa siendo `rental` en la beta y el radar puede versionarse, mostrarse y recibir preferencias desde el primer turno.

**Razón**: un estado adicional duplicaría transiciones y consultas sin aportar una diferencia de producto: la búsqueda parcial ya debe ser útil y durable.

**Alternativas descartadas**:

- Mantener sentinelas (`0` para ambientes o un presupuesto artificialmente alto): no distingue ausencia de preferencia de una decisión explícita y contamina explicaciones.
- Exigir completar el radar antes de activarlo: reproduce el formulario actual.

## Decisión 3 — Permitir una sesión antes de conocer el radar

**Decisión**: `ChatSession.search_profile_id` pasa a ser nullable. El primer acto significativo crea el radar y `ChatService.bind_profile(...)` lo enlaza una sola vez. Un nombre inicial determinista usa `Nueva búsqueda`, `Nueva búsqueda 2`, etc.; el usuario puede renombrarlo después.

**Razón**: la entrada primaria puede ser `/radar/new` sin fabricar un perfil inválido antes del primer mensaje. El nombre no depende del modelo ni bloquea la conversación.

**Alternativas descartadas**:

- Crear un radar vacío al abrir la pantalla: genera basura durable si la persona abandona.
- Pedir un nombre primero: agrega burocracia sin mejorar el matching.

## Decisión 4 — Interpretar actos múltiples, luego aplicar política determinista

**Decisión**: reemplazar el único intent de v3 por `ConversationInterpretation` v4 con una lista ordenada de actos. El modelo propone actos y confianza; código determinista valida autoridad, contexto, referencias y materialidad antes de ejecutar tools explícitas.

**Razón**: “sí, confirmo, y también quiero balcón” contiene dos actos legítimos. El modelo ayuda a entender lenguaje; no obtiene permiso para escribir libremente ni decidir ranking.

**Alternativas descartadas**:

- Ejecutar una tool por el intent dominante: pierde partes del mensaje.
- Permitir que el modelo escriba DB o calcule el ranking: rompe los límites arquitectónicos y la auditoría.

## Decisión 5 — Reanudar la acción pendiente con el texto completo

**Decisión**: conservar las propuestas durables y el checkpoint de LangGraph, pero eliminar el atajo HTTP de coincidencia exacta. Toda respuesta a una interrupción se reanuda con `{ "text": <mensaje completo> }`. El nodo `resolve_pending` interpreta primero aceptar/rechazar/editar y conserva los actos restantes para el mismo turno.

**Razón**: resuelve la causa directa del error donde “Confirmo” se confundía con feedback y evita descartar texto adicional. No agrega otra tabla de acciones pendientes que duplique propuestas y checkpoints existentes.

**Alternativas descartadas**:

- Un registro genérico nuevo de acciones pendientes: duplica lifecycle, expiración y auditoría ya presentes.
- Parsear “sí/no” en el router: mantiene conocimiento conversacional en la capa HTTP y no entiende respuestas naturales.

## Decisión 6 — Un orquestador profundo para el turno

**Decisión**: crear `ConversationTurnService` como interfaz pequeña que encapsula resolución de contexto, planificación de efectos, aplicación parcial, compilación y resumen. El grafo v4 coordina nodos; cada mutación sigue pasando por servicios de aplicación y puertos explícitos.

**Razón**: hoy la decisión se reparte entre router, compilador, grafo y tools. Una frontera profunda permite testear trayectorias sin FastAPI, LLM real ni DB.

**Alternativas descartadas**:

- Ampliar `CriteriaService`: ya mezcla catálogo, extracción, embeddings y recomputación; agregar conversación profundiza un módulo demasiado ancho.
- Agregar reglas aisladas al router: arregla ejemplos puntuales y conserva los loops sistémicos.

## Decisión 7 — Autoridad y confirmación son política, no copy del prompt

**Decisión**: versionar una política con jerarquía `explicit > deliberate_feedback > passive`, aplicación automática de cambios suaves/aditivos/reversibles y confirmación para filtros duros, contradicciones materiales o eliminaciones irreversibles. Las partes seguras de un mensaje se aplican aunque otra parte necesite aclaración.

**Razón**: la confirmación universal produce fricción; la confirmación ausente en cambios destructivos quita control. Una política pura permite probar ambos extremos.

## Decisión 8 — Semántica como señal congelada y de bajo peso

**Decisión**: una vinculación semántica guarda su embedding de consulta y versión. El scoring recibe, por cada listing y binding, una similitud calculada sobre embeddings persistidos. La contribución es siempre suave, multiplica score por confianza, tiene peso máximo `0.10` y nunca participa de gates de exclusión. Sin ambos embeddings compatibles, el resultado es `unknown` y aporta cero.

**Razón**: el scoring permanece puro y reproducible; el LLM no ordena resultados. Los refs de evaluación apuntan al binding, embedding de consulta y embedding del listing.

**Alternativas descartadas**:

- Ranking generativo: no es determinista ni auditable.
- Crear observaciones globales por frase del usuario: mezcla datos del listing con preferencias privadas y multiplica recomputaciones.

## Decisión 9 — Solo activar criterios que la persona declaró

**Decisión**: el documento de scoring aporta plantillas y pesos, pero los criterios opcionales solo se activan cuando existen en el perfil o compilación vigente. El score se normaliza por el peso total activo. Sin criterios evaluables, todos reciben score `0` y solo opera el tie-break estable.

**Razón**: hoy el policy puede puntuar luminosidad o balcón aunque la persona no los haya pedido. Con un radar parcial, dimensiones ausentes no deben fingir matches ni bajar confianza.

## Decisión 10 — Diagnóstico explícito de cero resultados

**Decisión**: el motor devuelve candidatos y conteos de exclusión por filtro duro. `RunDiagnostics` persiste esos conteos en las contribuciones/resumen del run. La respuesta propone relajaciones ordenadas por recuperación estimada, pero aplicarlas requiere un turno posterior.

**Razón**: una lista vacía necesita una causa auditable. Las preferencias suaves nunca forman parte de esos conteos.

## Decisión 11 — Coalescer trabajo, publicar solo la versión vigente

**Decisión**: persistir y versionar el radar sin esperar el run; antes de ejecutar un job, verificar que `profile.current_version_id == run.profile_version_id`. Los runs obsoletos terminan como `superseded` y no publican. El scheduler evita encolar otra ejecución si ya existe una más nueva para el perfil.

**Razón**: la idempotencia actual evita duplicados de la misma versión, pero no impide gastar trabajo ni publicar resultados de una versión anterior después de cambios rápidos.

## Decisión 12 — Evals de trayectorias y validación humana

**Decisión**: mantener v1 para comparabilidad y agregar conversaciones v2 con estado inicial, efectos por turno, estado final, invariantes y resultados prohibidos. El gate exige 100% de invariantes críticos, 95% global, 90% por familia. La transcripción reportada se vuelve caso canónico con variantes. La salida a beta también exige al menos ocho participantes, 80% de tareas sin ayuda, facilidad mediana 6/7, cero loops irrecuperables y correcciones visibles al turno siguiente.

**Razón**: los casos de un solo turno y tool matching no detectan pérdida de contexto ni escrituras en objetos equivocados.

## Decisión 13 — UI chat-first con estado visible

**Decisión**: `/radar/new` abre una sesión sin radar y muestra el chat como flujo principal; el editor estructurado queda disponible como alternativa. La UI usa primitivas shadcn de chat, muestra el radar activo y chips `Aplicado`, `Tentativo` y `Sin evidencia`. El input permanece montado y la actualización de resultados es no bloqueante.

**Razón**: el estado durable debe ser legible sin convertir cada turno en un formulario. La señal de progreso debe aparecer antes de un segundo.

**Nota de tooling**: `npx shadcn@latest info --json --cwd apps/web` agotó 30 segundos durante el diseño. `apps/web/components.json` confirma estilo Vega, RSC, Tailwind v4 y aliases `@/*`; la instalación de primitivas se hará y verificará durante implementación con acceso de red.

## Decisión 14 — Equidad antes de vincular o compilar

**Decisión**: el deseo original se conserva, pero la política de equidad puede producir binding `forbidden`, confianza cero y ninguna contribución. No se crean ni consultan conceptos como seguridad percibida, composición socioeconómica u otros proxies prohibidos.

**Razón**: preservar lo dicho no equivale a operacionalizar una característica dañina. La limitación debe ser explícita y corregible.
