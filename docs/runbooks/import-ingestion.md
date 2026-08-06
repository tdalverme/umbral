# Import Ingestion (Bronze)

Operación de la captura controlada de lotes (H2.1, UM-H2-001 a UM-H2-008).

## Alcance

Convierte un lote CSV/JSON controlado en snapshots crudos inmutables en Bronze,
cuarentena consultable y un reporte de calidad. La normalización Silver (H2.2)
es otro incremento.

- Contrato de importación v1: `contracts/import/v1/import-contract.json`
- Contrato operativo: `specs/002-bronze-ingestion/contracts/import-operations.md`
- Esquema: `specs/002-bronze-ingestion/data-model.md`

## Flujo

1. Un operador sube un archivo (CSV o JSON) a
   `POST /api/v1/imports/batches` con `source_id`, `source_version` y
   `contract_version`; opcionalmente una `batch_key` (por defecto es el
   SHA-256 del archivo).
2. El API crea un `import_run` en estado `pending`, conserva el archivo crudo
   como objeto inmutable (`ingestion/raw/<sha256>`) y encola el job durable
   `ingestion.import_batch`.
3. El worker valida cada registro contra el contrato, inserta
   `raw_listing_snapshots` y `quarantine_records`, deriva conteos y deja el run
   en `succeeded` (o `failed` con un código accionable).
4. El operador consulta `GET /api/v1/imports/runs/{run_id}` para progreso y
   `GET .../quality` (más `.../quality/download` en CSV) para calidad.

## Permisos

Todos los endpoints requieren sesión de producto con rol `operator` o
`administrator` (deny-by-default, acciones `ops.ingestion.*`). Un usuario sin
ese rol recibe 403. No se aceptan URLs; sólo subida de archivos.

## Idempotencia

- Repetir el mismo lote con la misma `batch_key` devuelve el mismo run sin
  efectos nuevos (el job replay terminal).
- El mismo contenido con otra clave crea un run nuevo pero cero snapshots
  duplicados gracias al único `(source_id, external_id, content_sha256)`.
- Un reintento tras una interrupción no duplica filas: los conteos se derivan
  de filas comprometidas y el write del archivo es content-addressable.

## Cuarentena y calidad

- Registros inválidos: `contract.required_field`, `contract.type_invalid`,
  `contract.enum_invalid`, `contract.range_invalid`, `contract.url_invalid`,
  `source.parse_error`.
- El reporte de calidad muestra `accepted`, `quarantined`, `duplicates`,
  `missing_fields`, campos faltantes por nombre y distribuciones anormales
  (outliers por IQR en price/surface_m2/rooms).

## Operación

- Los errores quedan en `import_runs.error_code` / `error_detail` y en el job
  (estado/intentos).
- El archivo crudo se conserva en object storage bajo
  `ingestion/raw/<file_sha256>` para auditoría y reparsing.
- La telemetría es metadata-only: nunca registra payload, ruta de archivo ni
  contenido.
