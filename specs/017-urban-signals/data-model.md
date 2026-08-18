# Data Model: Señales urbanas declarativas

## Principio

El modelo crece por filas de snapshots, categorías, señales y observaciones derivadas de un contrato declarativo versionado. No se agregan columnas por señal: el contrato define las señales y las observaciones las persisten con score, confidence, evidencia y versiones.

## Entidades nuevas

### UrbanContract

Representa el contrato declarativo versionado que define el dominio urbano.

| Campo | Tipo | Regla |
|---|---|---|
| `version_id` | UUID | PK, referenciado por las observaciones |
| `contract_version` | string | `urban-contract-v1`, versión global |
| `payload` | JSONB | Contrato completo (tags_mapping, primitivas, señales, normalización, confidence, fuente, atribución) |
| `status` | string | `active`, `superseded` |
| `source` | string | `geofabrik` |
| auditoría | mixin existente | actor, versión, timestamps, correlation id |

Invariantes:

- Un solo contrato `active` a la vez; un cambio de contrato supersede el anterior.
- Las observaciones citan el `version_id` del contrato que las generó.

### UrbanSnapshot

Instancia inmutable de datos de OpenStreetMap.

| Campo | Tipo | Regla |
|---|---|---|
| `snapshot_id` | UUID | PK |
| `source_path` | string | Ruta del archivo en object storage |
| `source_hash` | string | SHA-256 del archivo |
| `data_date` | datetime | Fecha de los datos (no de import) |
| `status` | string | `importing`, `ready`, `failed` |
| `poi_count` | int | Conteo de categorías importadas |
| `linear_count` | int | Conteo de features lineales importadas |
| auditoría | mixin existente | timestamps, correlation id |

### UrbanCategory (derivada del contrato)

Categorías de POI y features lineales definidas por el mapping de tags.

| Campo | Tipo | Regla |
|---|---|---|
| `category` | string | Clave de la categoría (ej. `cafe`) |
| `kind` | string | `poi` o `linear` |
| `osm_tags` | JSONB | Pares `[key, value]` de OpenStreetMap |
| `snapshot_id` | UUID | FK `urban_snapshots` |
| `osm_id` | string | Id del nodo/way fuente |

### UrbanPrimitive (derivada del contrato)

Métricas crudas por categoría y listing, calculadas desde las distancias.

| Campo | Tipo | Regla |
|---|---|---|
| `listing_id` | UUID | FK `silver_listings` |
| `snapshot_id` | UUID | FK `urban_snapshots` |
| `category` | string | Categoría de la primitiva |
| `kind` | string | `poi` o `linear` |
| `count_300m` | int | Conteo en el radio (cuando aplica) |
| `count_600m` | int | Conteo en el radio (cuando aplica) |
| `nearest_m` | float | Distancia al más cercano (cuando aplica) |

Índices:

- `(listing_id, snapshot_id)` para el batch de señales.
- `(category, snapshot_id)` para el cálculo de distancias.

### UrbanSignal (derivada del contrato)

Valor factual 0-1 por listing y señal.

| Campo | Tipo | Regla |
|---|---|---|
| `listing_id` | UUID | FK `silver_listings` |
| `snapshot_id` | UUID | FK `urban_snapshots` |
| `contract_version_id` | UUID | FK `urban_contracts` |
| `signal` | string | Nombre de la señal (ej. `walkability`) |
| `value` | float | Valor crudo 0-1 |
| `normalized_value` | float | Percentil del barrio (o global fallback) |
| `normalization_scope` | string | `barrio`, `caba` |
| `confidence` | float | Derivada de la cobertura de inputs |
| `missing` | boolean | Desconocimiento explícito |
| `contributors` | JSONB | Evidencia cruda: categorías con conteos y distancias |

Índices:

- `(listing_id, contract_version_id)` para el extractor.
- `(snapshot_id)` para el recálculo del batch.

### NeighborhoodSignalStats

Tabla de estadísticas precomputadas por barrio y señal.

| Campo | Tipo | Regla |
|---|---|---|
| `barrio` | string | Barrio normalizado |
| `signal` | string | Nombre de la señal |
| `sample_size` | int | Listings válidos del barrio |
| `normalization_scope` | string | `barrio` si `sample_size >= min_sample`, si no `caba` |
| `p50`, `p75`, `p90` | float | Percentiles del valor crudo |
| `snapshot_id` | UUID | FK `urban_snapshots` |

Índice: `(barrio, signal)`.

## Entidades modificadas

### ListingObservation

Agrega el soporte para observaciones urbanas:

- `extraction_version_id` apunta a la versión del contrato urbano (una `extraction_version` más).
- `matcher_type` puede ser `signal_score` para observaciones urbanas.
- `evidence` contiene los `contributors` (conteos y distancias por categoría).
- `source = "urban"`.

### Concept

Los concepts urbanos migran de `proxy` a `signal_ref`:

| Campo | Uso |
|---|---|
| `signal_ref` | Nombre de la señal del contrato (ej. `cafe_lifestyle`) |
| `matcher_type` | `signal_score` |
| `params` | Sin rangos de distancia (el score ya está normalizado) |

## Migración

- Crear `urban_contracts`, `urban_snapshots`, `urban_categories`, `urban_primitives`, `urban_signals`, `neighborhood_signal_stats`.
- Registrar el contrato `urban-contract-v1` como `extraction_version` (`kind=urban`, `artifact_version=urban-contract-v1`).
- Migrar los concepts `proximidad_cafes` y `acceso_transporte`: `proxy` → `signal_ref` (`cafe_lifestyle`, `transit_access`), `matcher_type` → `signal_score`.
- Reemplazar la tabla de señales urbanas actual (tipos fijos `cafe/transport/green_space`) por el modelo nuevo.
- Las observaciones urbanas existentes quedan fuera de vigencia (contrato viejo superseded).

## Flujo del batch

1. Importar snapshot OSM → `urban_snapshots` + `urban_categories`.
2. Calcular distancias por listing → `urban_primitives`.
3. Computar señales crudas → `urban_signals` (`value`).
4. Calcular percentiles por barrio → `neighborhood_signal_stats`.
5. Normalizar → `urban_signals.normalized_value` + `normalization_scope`.
6. Escribir `ListingObservation` para cada concept con `signal_ref` que tenga señal.
