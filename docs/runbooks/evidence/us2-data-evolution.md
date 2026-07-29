# Evidencia US2 — evolución de datos

| Campo | Resultado local |
| --- | --- |
| Revisión bootstrap | `0001_foundation_runtime` |
| Tablas foundation | `job_executions`, `job_attempts`, `job_outbox_messages`, `job_schedules`, `stored_objects`, `stored_object_versions`, `runtime_surface_status` |
| Extensiones | `postgis`, `vector` requeridas por el bootstrap |
| Head | único y lineal |
| Downgrade | declarado `empty-only` |
| Integridad | metadata SQLAlchemy y migration script comparten naming convention |
| Transacción | commit/rollback/close cubiertos por adapter in-memory; SQLAlchemy traduce `StaleDataError` |
| Conflicto | `ConcurrencyConflict` con versión esperada/observada |

## Comandos ejecutados

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m pytest tests/migrations tests/integration/db -q
.\scripts\check-migrations.ps1
```

El check de drift live queda condicionado a `DATABASE_URL`; no se marca como
pasado cuando el servicio PostgreSQL no está disponible. El bootstrap nunca se
ejecuta durante el arranque de API/web.

## Brecha de ejecución local

En esta evidencia no se ejecutó un contenedor PostgreSQL/Testcontainers: el
entorno no expuso `DATABASE_URL` ni un daemon Docker disponible. Por eso el
rollback transaccional sobre PostgreSQL, la comparación live de metadata y la
verificación real de versiones `postgis`/`vector` quedan pendientes del job de
CI/proveedor que habilite esas dependencias. Los contratos de metadata, el
bootstrap SQL offline, el UoW y el probe sanitizado sí se ejecutan localmente.
