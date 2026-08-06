# Research: Structured Search Radar

**Feature**: `004-structured-search-radar` | **Date**: 2026-08-06

Decisions recorded for the H2.3 increment (UM-H2-019 a UM-H2-034). Format per
item: Decision / Rationale / Alternatives considered.

## R-01 — Recommendation runs se ejecutan con el runtime durable de jobs

**Decision**: `recommendation.run` es un job asincronico del runtime durable
existente (`application/jobs` + outbox + lease + retries), publicado desde el
servicio de search profiles con `SubmitJob.create(...)` e idempotency key
`recommendation:{profile_id}:{profile_version_id}` (clarificacion 2026-08-06:
ejecucion asincronica). El handler procesa el candidate set, calcula scoring y
persiste items; el resultado del job es un resumen JSON <= 8 KiB con conteos.
El radar muestra el estado "generando resultados" (nuevo estado de run
`pending/running`) y publica via el patron `record_outcome` atomico.

**Rationale**: el runtime durable ya esta probado (imports/silver/identity),
da retry sin duplicados por identidad de job y publicacion atomica de
resultado; la clarificacion del spec fija el modelo asincronico y el umbral de
< 30 s. Un run fallido deja el ultimo run valido como unico resultado visible
(FR-013/FR-023).

**Alternatives**: sincronico en la request (rechazado: bloquea respuesta, no
congela inputs atomicamente, no se integra con el runtime de recovery);
hibrido con fallback (rechazado: complejidad sin beneficio en beta).

## R-02 — Candidate retrieval y paginacion estable

**Decision**: el candidate set se calcula una sola vez dentro del job del run
con una consulta SQL/PostGIS de solo lectura que aplica los hard filters
(budget por `total_cost`, zonas por `neighborhood`/`geometry` con PostGIS si
hay geometria, ambientes por `rooms`, superficie por `surface_m2`) y pagina
con `LIMIT/OFFSET` interno mientras recolecta. El resultado se congela en
`recommendation_items` con `position` 0..n. La paginacion de la UI pagina
sobre los items persistidos del run (`run_id` + `position` keyset, default 25,
max 100), por lo que es estable por construccion: los items no cambian entre
paginas salvo que el cliente cambie de run_id (SC-003: 0 repetidos/omitidos).

**Rationale**: congelar el candidate set en el run (UM-H2-027) hace la
paginacion trivialmente estable y auditable; el cliente recibe `run_id` y puede
reconsultar con el mismo run mientras navega.

**Alternatives**: paginar en vivo sobre Silver en cada request (rechazado:
los resultados podrian cambiar entre paginas y el orden no seria congelado);
cursor por valor de score (innecesario: los items ya estan persistidos y
ordenados).

## R-03 — Politica de desconocidos por hard filter (v1)

**Decision**: el search profile v1 define `unknown_strategy` por filtro,
versionada con el perfil: `price` -> `exclude` (un alquiler sin costo total no
es accionable y no puede validarse contra presupuesto); `location` -> `exclude`
(los barrios son requisito P0 del onboarding; listing sin barrio ni geometria
queda fuera); `rooms` -> `include` (ambientes suele faltar en fuentes y el
scoring lo penaliza con fit reducido); `surface` -> `include` (igual). Cada
estrategia es explicita en el contrato `search-profile-contract-v1` y se
documenta al crear/editar el radar (FR-009/FR-010, SC-002).

**Rationale**: el backlog exige politica explicita por filtro sin default
silencioso; estos defaults equilibran rigor (precio/ubicacion) con cobertura
(atributos frecuentemente ausentes), y son versionados e inmutables por
version de perfil.

**Alternatives**: desconocido siempre excluye (rechazado: cobertura baja en
CABA, campos faltantes comunes); siempre incluye (rechazado: violaria filtros
duros de precio/ubicacion); pregunta al usuario por cada caso (rechazado:
friccion en onboarding; la politica es por filtro, no por listing).

## R-04 — Scoring baseline v1

**Decision**: contrato `scoring-baseline-v1` versionado e inmutable:
dimensiones con pesos `budget 0.4`, `rooms 0.2`, `surface 0.2`,
`location_precision 0.2`. Funciones de fit deterministas: `budget_fit =
headroom = (budget - total_cost)/budget` recortado a [0,1]; `rooms_fit = 1.0`
si `rooms == min_rooms`, `0.85` si `rooms > min_rooms`, `0.5` si rooms
desconocido; `surface_fit = 1.0` dentro de [min,max], `0.8` si supera max
(hasta 1.5x) y `0.6` desde 1.5x; `location_precision_fit` por precision
Silver: exact 1.0, block 0.95, neighborhood 0.9, approximate 0.7, unknown 0.5.
Score total = suma ponderada redondeada a 4 decimales. Tie-break estable:
`(score desc, total_cost asc, listing_id asc)`. Cada item persiste
`contributions` JSONB con el desglose por dimension. El detalle del match
muestra el desglose sin presentarse como certeza; las cards muestran solo el
score total (clarificacion 2026-08-06, FR-012, SC-003, SC-012).

**Rationale**: determinismo puro y testable con casos golden; dimensiones
alineadas al perfil (presupuesto, zonas, ambientes, superficie); la precision
de ubicacion da senal util sin inventar coordenadas.

**Alternatives**: scoring con confianza/evidencia (H3, fuera de alcance);
pesos ajustables por usuario (especulativo en v1); embeddings (prohibido para
ranking por la constitucion).

## R-05 — Eventos de producto: contrato minimo versionado y tabla `product_events`

**Decision**: este incremento define `contracts/events/v1` con un registry
cerrado estilo `domain/identity/events.py` (event_type -> resultados/payload
permitidos, claves sensibles prohibidas) y persiste cada evento en una tabla
`product_events` con `occurred_at`, `actor`, `correlation_id` y payload
acotado sin PII. Eventos v1: `radar.created.v1` y
`recommendation.run_published.v1` (emitidos por el servidor, en la misma
transaccion del cambio o al publicar el run); `recommendation.impression.v1`,
`recommendation.detail_viewed.v1` y `listing.source_opened.v1` (emitidos por
el cliente via `POST /api/v1/product-events`, validados contra el registry).
UM-H0-013 queda como diccionario completo pendiente; este contrato es la
semilla versionada (supuesto del spec).

**Rationale**: los dashboards de activacion y precision percibida (H6-024,
H6-025) necesitan eventos persistentes consultables; un registry cerrado con
validacion da seguridad sin PII y versionado. La emision por el servidor en
transaccion evita eventos fantasma; la del cliente pasa por el BFF con el
mismo contrato.

**Alternatives**: solo telemetria (rechazado: no consultable, no auditable a
nivel producto); event bus/outbox general (rechazado: excede el minimo; la
tabla + registry cubre el guardrail de decision auditable); diccionario
completo UM-H0-013 (fuera de alcance del hito).

## R-06 — Proveedor de tiles del mapa

**Decision**: MapLibre GL con tiles raster publicos de OpenStreetMap
(`https://tile.openstreetmap.org/{z}/{x}/{y}.png`) con atribucion obligatoria.
El mapa es Client Component acotado; si el tile server falla, el mapa muestra
estado de error recuperable y la lista sigue operativa (FR-019). La eleccion
de un proveedor comercial/hosted y la politica CSP para tiles se evalua en
H6-013 (auditoria de headers) junto con el resto de la superficie.

**Rationale**: cero costo y cero secretos para beta privada de cohorte
pequena; el requisito funcional critico es la precision geografica autorizada
(SC-005), no el proveedor de tiles; precedente del repo: la eleccion de
proveedores se registra en el plan (geocoding en 003).

**Alternatives**: MapTiler/Mapbox (costo, key management, headers CSP desde
hoy; se difiere a H6); tiles auto-hosted (pesado, fuera de alcance).

## R-07 — Concurrencia y transiciones de estado del radar

**Decision**: edicion con optimistic locking (`expected_version` en PATCH,
`ConcurrencyConflict` 409 existente, FR-006). Transiciones v1: crear -> activo;
activo <-> pausado; activo/pausado -> archivado. Archivado es terminal en este
incremento (no se ofrece restaurar; conserva datos e historial, FR-003).
Pausar detiene nuevos runs; editar un radar pausado no dispara run hasta
reanudar; editar un radar activo invalida resultados vigentes y dispara run con
nueva version de perfil (FR-015).

**Rationale**: minimo alcance que satisface US2 (pausar/reanudar/archivar) sin
construir superficie especulativa; restaurar desde archivado es trivial de
agregar en H3 si la beta lo pide.

**Alternatives**: restaurar desde archivado (rechazado: no pedido en la spec);
transiciones libres sin maquina de estados (rechazado: invariantes difusas).

## R-08 — Limite de radares y tamano de datos

**Decision**: sin limite duro de radares por usuario en beta; el listado pagina
(50 por pagina). Sin rate limits de producto en este incremento (el limiter de
identidad solo cubre magic links; los rate limits de producto son H4-029/H6).
Los runs operan sobre el conjunto controlado de beta (fixture de referencia +
listados CABA, miles de listings); el target de < 30 s se verifica sobre el
conjunto de prueba con indice de candidatos en `recommendation_items`.

**Rationale**: el backlog no define limite; la beta es cohorte pequena y el
volumen de datos es el del dataset controlado.

**Alternatives**: limite de N radares (dato inventado); cache de resultados
(prematura hasta medir).

## R-09 — Contratos HTTP: prefijo `/api/v1` y actualizacion de docs

**Decision**: los nuevos routers usan `APIRouter(prefix="/api/v1")`, igual que
auth/imports implementados, con `operationId` camelCase y schemas Pydantic
`extra="forbid"`. Se actualiza `docs/api/endpoints.md` para reflejar las rutas
implementadas (el doc anticipaba rutas sin `/v1`; la practica del repo es
`/api/v1`, y el contrato OpenAPI major 1 ya lo fija). El OpenAPI se exporta con
`scripts/export-openapi.ps1` y el cliente web se regenera con `api:generate`
(UM-H1-005; el cliente generado se commitea y el drift lo bloquea `api:check`).

**Rationale**: consistencia con la superficie existente y con el gate
anti-breaking; el contrato OpenAPI ya declara `contract_major=1`.

**Alternatives**: rutas sin version (`/api/search-profiles` como anticipaba el
doc): generaria dos convenciones en el mismo contrato y romperia la
consistencia del cliente generado.

## R-10 — Onboarding y forms sin dependencias nuevas

**Decision**: el onboarding usa forms controlados con los primitives shadcn
existentes (`field`, `input`, `alert`, `button`) y validacion nativa del
navegador + validacion de negocio tipada desde la API; no se agregan
react-hook-form/zod/Radix en este incremento. El flujo es de 3 pasos
(presupuesto y operacion; zonas CABA; requisitos P0: ambientes y superficie) +
resumen con confirmacion explicita (FR-007). Zonas de CABA v1: lista cerrada
de 15 barrios (CABA) definida en el contrato del perfil; una zona sin geometria
en Silver trata el listing por su `neighborhood`.

**Rationale**: minimo cambio sobre la base instalada; los primitives actuales
cubren labels, errores accesibles y focus; la validacion de negocio vive en el
contrato HTTP y es testeable.

**Alternatives**: react-hook-form + zod (dependencias nuevas, beneficio
marginal en 3 pasos simples); Select/combobox con Radix (se agrega cuando la
densidad de datos lo pida, H3+).

## R-11 — Autenticacion web del radar: cliente react-query y BFF

**Decision**: se monta `QueryClientProvider` en la app y se usa el cliente
generado (hey-api) con el client de browser apuntando al origin (patron BFF ya
creado en `src/lib/api/browser.ts`): las paginas del radar llaman rutas BFF que
proxyan a `/api/v1` con la cookie de sesion (mismo patron que identity). Las
rutas de producto viven dentro de `(protected)`. El refresh de estado del run
se hace con polling corto mientras `status in (pending, running)` (intervalo
3 s, maximo 30 s) y luego react-query refetch on focus.

**Rationale**: reutiliza el patron BFF probado de identity, evita duplicar
DTOs (cliente generado) y da estados de carga reales para el run asincronico.

**Alternatives**: fetch directo a la API (rompe el patron de cookie/BFF y el
cliente tipado); WebSocket/SSE para estado del run (innecesario con target
< 30 s).

## Decisiones diferidas a fases posteriores (registradas)

- Proveedor comercial de tiles y CSP de tiles: H6-013.
- Rate limits de producto y fatiga de alertas: H4-029 / H5.
- Diccionario completo de eventos y metricas (UM-H0-013): contrato completo
  cuando H0 lo publique; este incremento lo precede con la semilla v1.
- Restaurar radares archivados y limite por usuario: revisar con datos de beta.
