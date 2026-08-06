# Evidencia de aceptación: Silver Normalization

**Feature**: `003-silver-normalization` | **Fecha**: 2026-08-06
**Alcance**: UM-H2-009 a UM-H2-018 (épica H2.2) | **Harness**: `.\scripts\check.ps1` y `scripts\check-silver.ps1`

## Chequeos ejecutados (2026-08-06, local + Docker Desktop)

```powershell
uv run ruff check src tests                      # PASS en todo el feature; solo 4 lint pre-existentes
                                                 # en ops/* y tests/unit/api/test_dependencies.py
uv run mypy src tests                            # PASS en los 18+ archivos del feature y del fix de
                                                 # objects/ingestion; 23 errores pre-existentes en
                                                 # identity/ops (archivos no tocados)
uv run pytest tests/unit tests/contract tests/migrations tests/architecture
   (excluyendo 3 archivos con fallos pre-existentes de entorno)   # 299 PASS
uv run pytest tests/unit/application/silver tests/unit/infrastructure/test_geocoding.py \
   tests/contract/test_silver_schema.py tests/contract/test_dedupe_policy.py \
   tests/migrations/test_0004_silver.py tests/architecture/test_silver_boundaries.py  # 55 PASS
uv run pytest tests/integration/silver           # 12 PASS (Docker local)
uv run pytest tests/integration/object_store tests/contract/test_object_store.py  # 18 PASS
```

**Resultado clave**: los **12 tests de integración Silver pasan con Docker Desktop local**
(Postgres 17 + PostGIS vía testcontainers, migración 0001→0004 al head):
normalization pipeline, dedupe golden (determinista + propuestas), changes con
before/after/origen, geocoding con guard de precisión, lineage Bronze-Silver y
reproceso idempotente (SC-008, incluida la nueva `normalizer_version`).

El set completo de `scripts/check-silver.ps1` (unit + contract + migrations +
integración) suma **60 PASS** con Docker local. La ejecución del propio script
`check-silver.ps1` sin `--basetemp` falla en esta máquina por un `PermissionError`
del directorio `%TEMP%\pytest-of-Usuario` (afecta a todo `tmp_path` de pytest en
Windows local, también a `check-imports.ps1`); en CI/Linux no aplica. Por eso la
evidencia se corrió con `--basetemp` en un dir limpio del proyecto.

## Fix quirúrgico aplicado (Bronze, pre-existente)

Para poder correr la integración E2E se corrigió un defecto pre-existente de
`002-bronze-ingestion` que impedía escribir/leer el archivo crudo en cualquier
object store real:

- `raw_storage_key` pasó de `ingestion/raw/<sha256>` a `objects/raw/<sha256>`
  (los adapters filesystem y S3 exigen keys `objects/<id>/<version>`);
- `_capture` resuelve el ref vía `ObjectStore.ref_for_key(...)` (los refs del
  adapter filesystem son tokens opacos) en lugar de
  `ProviderObjectRef(raw_storage_key)`;
- se agregó `ref_for_key` al protocolo `ObjectStore` (S3 y filesystem ya lo
  implementaban; `InMemoryObjectStore` de tests también).

Actualizaciones asociadas: `tests/unit/application/ingestion/test_import_run_service.py`
(assert de prefijo), `docs/runbooks/import-ingestion.md` y
`docs/runbooks/evidence/bronze-ingestion-acceptance.md` (formato de key).
Los 46 unit tests de Bronze siguen verdes.

**Pendiente pre-existente (NO bloquea Silver)**: los tests de integración de
Bronze que usan `InMemoryJobRuntime` contra Postgres real fallan por FK
`import_runs.job_execution_id` (la ejecución del job existe solo en memoria).
Es un defecto de la suite de Bronze, ajeno a H2.2.

## Trazabilidad FR/SC → evidencia

| Criterio | Evidencia automatizada | Estado |
| --- | --- | --- |
| SC-001 listings Silver con identidad/referencia | `test_reference_batch_normalizes_to_silver_end_to_end` (integración) + unit | PASS |
| SC-002 atributos validados, sin coerción | `test_out_of_range_attributes_are_recorded_not_coerced` | PASS |
| SC-003 precio sin conversión | `test_price_and_currency_are_preserved_verbatim` + `test_unsupported_currency_is_recorded_not_converted` | PASS |
| SC-004 dedupe determinista vs propuestas, cero auto-merges | `test_deterministic_and_proposal_links_on_real_backend` (integración) + `test_exact_cross_source_duplicates_share_one_canonical` | PASS |
| SC-005 cambios with before/after/origen | `test_price_and_text_changes_are_recorded_with_before_after_origin` (integración) | PASS |
| SC-006 geocoding/precisión | `test_geocoding_upgrades_only_allowed_granularity` (integración) + `tests/unit/infrastructure/test_geocoding.py` | PASS |
| SC-007 lineage Bronze-Silver | `test_every_reference_entity_walks_back_to_snapshot_and_run` (integración) | PASS |
| SC-008 reproceso idempotente | `test_reprocess_idempotency.py` (integración) + `test_reprocess_is_idempotent` | PASS |

## Cambios de contratos y datos

- Contratos publicados: `contracts/silver/v1/silver-schema.{json,md}`,
  `contracts/dedupe/v1/dedupe-policy.{json,md}` (inmutables una vez ratificados).
- Migración `0004_silver_normalization` (down: `0003_bronze_ingestion`) con 4
  tablas y 8 ENUMs; head único verificado por `test_migration_graph_has_one_linear_head`.
- Nuevos settings `SILVER_GEOCODING_*` (deshabilitados por default).

## Guardrails de beta

- Lineage completo: cada entidad Silver recorre snapshot y parser (SC-007) — verificado.
- Dedupe no destructivo: propuestas ambiguas nunca se fusionan (SC-004) — verificado.
- Sin LLM, sin SQL libre desde el agente, sin acceso de agentes a Silver.
- Fallos pre-existentes ajenos a este incremento (confirmados en `main` sin los
  cambios): `test_supabase_adapter`, `test_cli::test_rq_worker_uses_umbral_queue_and_json_serializer`,
  `test_openapi_versioning`, `tests/unit/ops/test_release_ops.py`, y la suite de
  integración de Bronze con `InMemoryJobRuntime` (FK `job_execution_id`).
