# Research: Silver Normalization

**Feature**: `003-silver-normalization` | **Date**: 2026-08-06

Design decisions and rejected alternatives for the H2.2 increment. Each entry:
Decision / Rationale / Alternatives considered.

## 1. Disparo de la normalizacion

- **Decision**: la normalizacion se ejecuta como un job durable
  `ingestion.normalize_batch` encadenado a la finalizacion exitosa de un
  `import_run` de H2.1: el worker de importacion, al completar el run, publica
  el job de normalizacion via outbox en la misma transaccion (publish-before-
  commit, mismo patron que foundation runtime).
- **Rationale**: el hito exige "operador importa → entidades Silver"; el job
  durable hereda at-least-once, lease, reintentos acotados y clasificacion de
  fallos. La idempotencia por identidad de job se suma a la unicidad
  `(snapshot_id, normalizer_version)` para que reintentos intermedios nunca
  dupliquen entidades (SC-008).
- **Alternatives**: disparo manual por operador (requiere superficie nueva sin
  UI en alcance y deja Silver vacia si nadie dispara); sincronico dentro del
  job de importacion (acopla tiempos y reintentos de dos dominios en uno).

## 2. Forma de las entidades Silver

- **Decision**: una fila `silver_listings` por snapshot normalizado, inmutable y
  aditiva, con unicidad `(snapshot_id, normalizer_version)`; las columnas
  filtrables (precio, superficie, ambientes, dormitorios, piso, tipo, operacion,
  amenities, ubicacion) quedan tipadas y no en un JSONB generico.
- **Rationale**: H2.3 (UM-H2-024/025) aplica hard filters y paginacion estable
  con SQL/PostGIS sobre estas columnas; tipar ahora evita re-migrar despues.
  La inmutable-aditividad replica el patron Bronze y permite reprocesar con
  nueva version de normalizador conservando las filas previas (UM-H6-004).
- **Alternatives**: atributos en JSONB (flexible pero obliga casting y
  validacion ad hoc en el query path de hard filters); tabla unica mutable
  (viola inmutabilidad y la correccion silenciosa prohibida).

## 3. Identidad canonica y dedupe deterministico

- **Decision**: dos capas.
  1. Dentro de una fuente, `(source_id, external_id)` resuelve siempre a la
     misma property canonica (cadena de publicaciones).
  2. Entre fuentes, el dedupe deterministico usa un fingerprint fuerte:
     `operation + property_type + price + currency + surface_m2 + rooms +
     bedrooms + neighborhood_normalizado`; el vinculo es deterministico solo si
     TODOS los campos fuertes estan presentes y coinciden exactamente.
     Cualquier campo faltante degrada el caso a propuesta.
- **Rationale**: el fingerprint fuerte sin campos faltantes cumple "identidad
  de fuente/hash/datos fuertes" (UM-H2-015) con reglas explicitas y versionadas;
  la degradacion a propuesta protege de fusionar falsos positivos (patron
  prohibido: dedupe destructivo sin confianza).
- **Alternatives**: similitud de direccion textual como determinante (frágil
  ante typos y formatos; es trabajo de propuestas); solo mismo external_id
  entre fuentes (no existe en la practica: cada fuente usa ids propios);
  distancia geografica < N metros como determinante (mezcla precision de
  ubicacion con identidad; peligro de falsos positivos).

## 4. Dedupe probabilistico no destructivo (P1, UM-H2-016)

- **Decision**: propuestas por reglas deterministicas de similitud sobre campos
  normalizados (solapamiento de tokens de direccion, razon de precio,
  razon de superficie, diferencia de ambientes), con score 0..1, evidencia por
  dimension y estado `pending`; transicion a `confirmed`/`rejected` solo via
  operacion interna con lock optimista y auditoria. Ningun caso `pending` se
  fusiona. La superficie de revision visual queda fuera de alcance (assumption
  de la spec).
- **Rationale**: reglas versionadas y testeables sin LLM; el score y la
  evidencia son auditables; sin UI no hay necesidad de endpoint HTTP en este
  incremento.
- **Alternatives**: embeddings/similitud vectorial (prohibido como sustituto y
  sin necesidad en v1); auto-fusion con score alto (viola "no fusiona
  automaticamente casos ambiguos").

## 5. Deteccion de cambios entre versiones

- **Decision**: se comparan filas consecutivas de la misma cadena
  `(source_id, external_id)` ordenadas por `captured_at`; por campo normalizado
  que difiera se emite `listing_changes` con before/after/origen. "Estado" solo
  se compara cuando una version futura del contrato lo defina (clarificacion de
  la spec). Reprocesar el mismo snapshot con nuevo normalizador solo emite
  cambios si los valores realmente difieren.
- **Rationale**: before/after/origen es exactamente lo que piden UM-H2-017 y la
  traza para historial (H3-031) y alertas de baja de precio (H5-005).
- **Alternatives**: diff contra el snapshot crudo (mezcla normalizacion con
  cambio de parser); diff solo de precio (la spec pide texto y atributos).

## 6. Geocodificacion (P1, UM-H2-013)

- **Decision**: puerto `Geocoder` con adapter `NominatimGeocoder` (OpenStreetMap)
  detras de cache LRU en proceso y rate limiter token-bucket; la precision
  resultante nunca supera la granularidad del input (full address →
  exact/block, barrio → neighborhood, sin barrio → unknown). El runtime local
  usa `FakeGeocoder`; el adapter real se habilita por configuracion (deshabilitado
  por default). Fuente registrada `osm.nominatim` en cada resultado.
- **Rationale**: sin API key ni costo para beta, con ToS permisivas para uso
  acotado; cache y rate limits explicitos cumplen la letra de UM-H2-013; el
  contrato de precision evita "mejorar artificialmente" (spec FR-008).
- **Alternatives**: Google Maps / Mapbox (API key, costo, y ToS de geocoding
  con restricciones de uso en listados; decision comercial posterior);
  geocoding local con OSM data (heavy para beta). httpx ya es dependencia
  runtime; no se agregan librerias.

## 7. Versionado del normalizador

- **Decision**: `normalizer_version` inmutable por fila Silver, derivada de los
  loaders versionados `silver-schema-v1` y `dedupe-policy-v1` (igual patron que
  `parser_version` en H2.1). Cambios de reglas → nueva version; reproceso crea
  filas nuevas y conserva las previas.
- **Rationale**: reproducible y auditable (constitucion II y V); se alinea con
  UM-H6-004 sin construir el reprocess controlado completo, que es del hito H6.
- **Alternatives**: columna mutable (rompe auditoria); version en tabla aparte
  (sobre-ingenieria sin evidencia de necesidad).

## 8. Superficie de consulta

- **Decision**: sin endpoints HTTP en este incremento. El servicio expone
  lecturas (listing por id, cadena de publicaciones, changes, dedupe links por
  estado, lineage walk) consumidas por tests y por el harness
  `scripts/check-silver.ps1`.
- **Rationale**: la spec excluye superficies de usuario final y el principio de
  cambio minimo prohibe features no pedidas; H2.3 expone los contratos HTTP de
  matches y H6.3 la consola de import runs. Los tests integrados y el harness
  prueban el comportamiento observable de producto.
- **Alternatives**: router de operador de solo lectura (superficie nueva sin
  usuario real; se posterga a la consola H6-003); lecturas solo por SQL manual
  (no auditable ni testeable como contrato).

## 9. Transaccionalidad del job de normalizacion

- **Decision**: el handler normaliza en una transaccion por lote pequeno
  (rebanadas de snapshots): inserta `silver_listings`, resuelve/crea
  `canonical_properties`, emite `dedupe_links` y `listing_changes`, todo con
  locks optimistas y unicidades que arbitran reintentos parciales.
- **Rationale**: reintento intermedio nunca duplica ni deja cambios huerfanos
  (SC-008); el patron replica H2.1.
- **Alternatives**: una transaccion por run completo (contention innecesaria);
  dos fases con estado intermedio persistido (complejidad sin necesidad).

## 10. Telemetria y auditoria

- **Decision**: los eventos versionados de normalizacion (run iniciado,
  entidades creadas, cambios emitidos, links creados/transicionados, fallo con
  causa) se emiten con el allowlist de metadatos existente; ninguna fila Silver
  ni payload entra a logs o trazas. Las operaciones de confirmacion/rechazo de
  propuestas registran actor y correlacion.
- **Rationale**: DoD comun item 4 y guardrail de lineage completo 100%.
- **Alternatives**: logs detallados de valores (viola el filtro de PII y el
  principio de minimo contenido en logs).
