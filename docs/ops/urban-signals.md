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

## Importador osmium

`src/umbral/infrastructure/urban/osm_importer.py` parsea nodos/ways del pbf,
clasifica por `tags_mapping`/`linear_tags_mapping` del contrato y persiste cada
elemento como una fila `urban_categories` (kind `poi`/`linear`, geometría
POINT). La clasificación es pura (`classify`) y testeable sin un pbf real.
`osmium` es una dependencia opcional: si no está instalado, el import reporta
un error claro en el momento de importar, sin romper el resto de la app.

## Reimport y recálculo

- Registrar una nueva versión del contrato (o reimportar) supersede la anterior
  e invalida las observaciones urbanas previas (`invalidate_active_for_source`),
  de modo que las señales viejas nunca se muestran como vigentes.
- Un snapshot reimportado (nuevo hash/fecha) recalculca el 100% de los listings
  con coordenadas: el job `urban.batch` usa el snapshot activo (último `ready`)
  y `replace_for_contract` reemplaza todas las filas de señales del contrato.
- El evento `urban.import_completed.v1` registra el run del import
  (`snapshot_id`, `listings_processed`, `published_count`).

## Atribución y licencia

El contrato declara `source.name`, `source.attribution` y `source.license`
(ODbL 1.0). La atribución se expone en `GET /api/v1/urban/signals` y se muestra
en el footer global del frontend (`© OpenStreetMap contributors`), enlazando a
https://www.openstreetmap.org/copyright.

## Verificación

```powershell
.\scripts\check.ps1       # incluye el check "Urban"
```
