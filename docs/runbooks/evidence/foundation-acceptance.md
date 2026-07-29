# Matriz de aceptación foundation-runtime

| Área | Evidencia | Resultado |
| --- | --- | --- |
| Configuración y release | `tests/unit/config`, manifest y runbook local | PASS |
| API/probes/correlación | `tests/contract`, `/health`/`/ready`/`/version` | PASS |
| Web accesible | Vitest, lint, typecheck y Playwright collection | PASS |
| PostgreSQL/Alembic | migración offline, snapshots, 55 focales DB | PASS; live requiere DATABASE_URL |
| Jobs/queue | 22 focales, JSON-only, leases/retry/scheduler | PASS |
| Object storage | 11 focales filesystem + fake S3 | PASS; MinIO real requiere Docker |
| Recovery | backup/restore/checksums/RPO-RTO local | PASS; remoto requiere credenciales |
| Observabilidad | filtering, Sentry, web metadata-only, trace | PASS |
| Delivery | manifest, access, lock, smoke, rollback, workflows | PASS local; providers remotos no ejecutados |

Las limitaciones externas no se convierten en falsos verdes: están
registradas en los runbooks y mantienen el código fail-closed.
