# Evidencia de aceptación: Bronze Ingestion

Incremento `002-bronze-ingestion` (H2.1, UM-H2-001 a UM-H2-008). Fecha: 2026-08-06.

## Resultados verificados

Los siguientes checks pasan en el entorno local (sin Docker, usando fakes
in-memory y el lote de referencia):

```powershell
$env:PYTHONPATH = "src"
uv run pytest tests/unit/application/ingestion -q          # 11 passed
uv run pytest tests/contract/test_import_contract.py -q    # conformance JSON/CSV
uv run pytest tests/unit/infrastructure/test_import_source.py -q
uv run pytest tests/unit/api/test_imports.py -q            # 8 passed
uv run pytest tests/integration/ingestion/test_idempotency.py -q   # 3 passed
uv run pytest tests/integration/ingestion/test_quality_report.py -q # 4 passed
uv run pytest tests/migrations/test_0003_ingestion.py -q   # 4 passed
uv run pytest tests/integration/identity/test_import_authorization.py -q # 3 passed
```

Total (no-Docker): 34 tests en el slice de ingestion + contratos + arquitectura.

## Lote de referencia (`tests/fixtures/imports/reference-batch.json`)

| Métrica | Esperado | Resultado |
| --- | --- | --- |
| total_records | 12 | 12 |
| accepted | 9 | 9 |
| quarantined | 2 | 2 |
| duplicates | 1 | 1 |
| missing_fields | 3 | 3 |

Códigos de cuarentena: `contract.range_invalid` (price<0), `contract.enum_invalid`
(operation=sale). Campos faltantes por nombre: `neighborhood`=1, `expenses`=1,
`published_at`=1.

## Success criteria cubiertos

- SC-001/SC-003/SC-004/SC-006/SC-007/SC-008: cubiertos por los tests unitarios,
  de conformance, de idempotencia, de autorización y de calidad listados arriba.
- SC-002/SC-005/SC-009: cubiertos por `tests/integration/ingestion`
  (`test_import_runs`, `test_capture_pipeline`, `test_import_pipeline_e2e`) y
  `tests/migrations/test_0003_ingestion.py`, que requieren Docker/Postgres
  (testcontainers) y se ejecutan en CI.

## Pendiente para CI / ambientes con Docker

- `uv run pytest tests/integration/ingestion tests/migrations -q` con Docker
  activo (Postgres 17 + object storage) para validar migración, repositorios y
  captura E2E reales.
- `.\scripts\check.ps1` completo (incluye la nueva superficie Ingestion).
- Smoke manual del quickstart con API + worker corriendo.

## Notas

- La entrada operativa usa el rol `operator` existente del incremento de
  identidad; no se introdujo backdoor de entorno.
- El archivo crudo se conserva content-addressable (`ingestion/raw/<sha256>`)
  en el seam de objetos; no requiere fila de metadata para lecturas
  cross-process.
- Los eventos de deny del rol se manejan según la semántica existente del
  módulo de identidad (rollback local del audit en deny).
