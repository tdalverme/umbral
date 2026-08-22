# Runbook: Señales urbanas (operación del snapshot)

**Feature**: `017-urban-signals` | **Rama**: codex/conversational-search-copilot | **Fecha**: 2026-08-17

Operación del ciclo de datos urbanos de OpenStreetMap: descarga, verificación,
importación, reimportación, recálculo y atribución. Complementa
[structured-search-radar.md](../runbooks/structured-search-radar.md).

## Comando de ops

El comando `python -m umbral.ops.urban` descarga el snapshot, computa su
SHA-256, lo sube a object storage y dispara la importación:

```powershell
$env:PYTHONPATH = "src"
python -m umbral.ops.urban --fetch --import
```

Opciones:

| Flag | Descripción |
| --- | --- |
| `--fetch` | Descarga `argentina-latest.osm.pbf` desde Geofabrik a `.data/`. |
| `--import` | Sube el archivo a `objects/urban/<sha256>.osm.pbf`, importa categorías y encola el job `urban.batch`. |
| `--rebuild-active` | Reparsea el PBF de `urban_snapshots.source_path`, reemplaza las categorías y derivados del snapshot activo y encola `urban.batch`; no descarga ni crea otro snapshot. |
| `--url` | URL del snapshot (default: Geofabrik South America / Argentina). |
| `--dest` | Ruta local del snapshot. |
| `--prefix` | Prefijo de object storage (default `objects/urban`). |
| `--date` | Fecha de datos del snapshot (ISO-8601). |

### Flujo

1. Se descarga el `.osm.pbf` (fail-fast si el HTTP no es 200).
2. Se computa el SHA-256 del archivo.
3. Se sube a object storage con `put_if_absent(storage_key, sha256, size, ...)`.
4. `import_snapshot` crea la fila `urban_snapshots` (status `importing`),
   ejecuta el importador osmium para poblar `urban_categories`, la marca
   `ready` y encola el job `urban.batch` (auditable en el job runtime).

### Reprocesar el snapshot existente

Después de desplegar una versión con cambios de Urban, el reproceso correctivo
en Railway es:

```powershell
alembic upgrade head
python -m umbral.ops.urban --rebuild-active
```

`--rebuild-active` reutiliza el objeto inmutable indicado por
`urban_snapshots.source_path` (por ejemplo,
`objects/urban/<sha256>.osm.pbf`). Conserva el `snapshot_id`, `source_hash` y
la metadata de origen; no vuelve a consultar Geofabrik. El PBF se parsea en un
staging local y recién después se reemplazan, en una transacción, las
categorías, primitivas, señales y estadísticas de ese snapshot. Si el parseo
falla no se borra el conjunto anterior ni se encola el batch.

El batch posterior recalcula todos los listings con coordenadas precisas. Las
señales quedan identificadas por listing, snapshot y contrato, por lo que los
resultados de snapshots anteriores siguen siendo auditables.

## Importador osmium

`src/umbral/infrastructure/urban/osm_importer.py` parsea nodos/ways del pbf,
clasifica por `tags_mapping`/`linear_tags_mapping` del contrato y persiste cada
elemento como una fila `urban_categories` (kind `poi`/`linear`). Los POI usan
POINT y los ways lineales usan una LINESTRING construida con todos sus nodos
válidos; las distancias se calculan contra la geometría real. La categoría
`subway_station` solo acepta `station=subway`, no las entradas
`railway=subway_entrance`, y `subway_line` conserva cada way OSM como fuente
auditable sin sumar segmentos como estaciones o líneas distintas. La
clasificación es pura (`classify`) y testeable sin un pbf real.
`osmium` es una dependencia opcional: si no está instalado, el import reporta
un error claro en el momento de importar, sin romper el resto de la app.

## Reimport y recálculo

- Registrar una nueva versión del contrato (o reimportar) supersede la anterior
  e invalida las observaciones urbanas previas (`invalidate_active_for_source`),
  de modo que las señales viejas nunca se muestran como vigentes.
- Un snapshot reimportado (nuevo hash/fecha) recalculca el 100% de los listings
  con coordenadas: el job `urban.batch` usa el snapshot activo (último `ready`)
  y reemplaza solo las filas de señales del par snapshot/contrato.
- Los campos de conteo no declarados por el contrato quedan en `NULL`; no
  representan un conteo observado igual a cero.
- El evento `urban.import_completed.v1` registra el run del import
  (`snapshot_id`, `listings_processed`, `published_count`).

## Atribución y licencia

El contrato declara `source.name`, `source.attribution` y `source.license`
(ODbL 1.0). La atribución se expone en `GET /api/v1/urban/signals` y se muestra
en el footer global del frontend (`© OpenStreetMap contributors`), enlazando a
https://www.openstreetmap.org/copyright.

## Verificación

Controles útiles después del reproceso, ejecutados contra la misma base:

```sql
-- No debe devolver filas.
SELECT snapshot_id, osm_id, category, COUNT(*)
FROM urban_categories
WHERE snapshot_id = '<SNAPSHOT_ID>'
GROUP BY snapshot_id, osm_id, category
HAVING COUNT(*) > 1;

-- Los ways lineales deben ser LINESTRING.
SELECT COUNT(*)
FROM urban_categories
WHERE snapshot_id = '<SNAPSHOT_ID>'
  AND kind = 'linear'
  AND ST_GeometryType(geometry) <> 'ST_LineString';

-- Las entradas no deben alimentar subway_station.
SELECT COUNT(*)
FROM urban_categories
WHERE snapshot_id = '<SNAPSHOT_ID>'
  AND category = 'subway_station'
  AND tags ->> 'railway' = 'subway_entrance';

-- Las métricas no soportadas son NULL, no cero sintético.
SELECT count_300m, count_600m
FROM urban_primitives
WHERE snapshot_id = '<SNAPSHOT_ID>'
  AND category = 'subway_line';
```

```powershell
.\scripts\check.ps1       # incluye el check "Urban"
```
