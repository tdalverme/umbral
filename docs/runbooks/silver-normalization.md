# Runbook: Normalización Silver

**Feature**: `003-silver-normalization` | **Rama**: main | **Fecha**: 2026-08-06

Cómo opera la capa Silver: normalización automática, dedupe, cambios y
reproceso. Complementa [import-ingestion.md](./import-ingestion.md).

## Pipeline

1. Un `import_run` de H2.1 termina `succeeded`.
2. El handler `ingestion.import_batch` publica el job encadenado
   `ingestion.normalize_batch` (outbox, idempotente por identidad
   `logical_target=<run_id>`).
3. El worker `SilverNormalizeHandler` procesa los snapshots del run:
   - cada snapshot se normaliza contra `silver-schema-v1` (sin conversión de
     moneda, sin inventar datos, precisión declarada);
   - se inserta una fila inmutable `silver_listings` por
     `(snapshot_id, normalizer_version)`;
   - se resuelve la property canónica (cadena `(source_id, external_id)` y
     dedupe determinista entre fuentes por fingerprint);
   - se emiten `listing_changes` (before/after/origen) entre versiones
     consecutivas de la misma cadena;
   - se crean `dedupe_links` (deterministas `confirmed`, ambiguos `pending`).

## Operaciones comunes

### Reprocesar un run (misma normalizer_version)
Reejecutar el job `ingestion.normalize_batch` para el mismo run no crea filas
nuevas: el unique `(snapshot_id, normalizer_version)` arbitra (SC-008). No hay
acción manual necesaria; el reintento del runtime es idempotente.

### Reprocesar con una nueva versión del normalizador
Cargar la nueva `silver-schema-v1` (ej. `silver-schema-v1.beta`) y disparar el
job sobre los snapshots seleccionados: crea filas nuevas y conserva las
anteriores (UM-H6-004). La revisión visual de propuestas de dedupe es posterior
a este incremento; aquí los links son consultables por estado.

### Confirmar / rechazar una propuesta de dedupe
Operación de servicio `confirm_link`/`reject_link` con lock optimista
(`WHERE id AND version`) y auditoría de actor. Solo los links `confirmed`
resuelven canonical; los `pending` nunca fusionan.

### Geocodificación
Deshabilitada por default (`SILVER_GEOCODING_ENABLED=false`). Al habilitarla se
usan cache, rate limits y una fuente registrada; la precisión nunca mejora la
granularidad del input. Un fallo del proveedor degrada a `unknown` sin bloquear
el lote.

## Verificación

```powershell
uv run pytest tests/unit/application/silver tests/contract/test_silver_schema.py tests/contract/test_dedupe_policy.py tests/integration/silver
.\scripts\check.ps1
```

## Datos y lineage

- `silver_listings.snapshot_id` → `raw_listing_snapshots` →
  `import_runs` (lineage Bronze-Silver, SC-007).
- Ninguna fila Silver se actualiza; una corrección inserta una nueva versión.
- Auditoría: `actor_kind`/`actor_id`/`source`/`correlation_id` en cada fila;
  sin valores normalizados ni payloads en logs.
