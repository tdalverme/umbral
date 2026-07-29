# Evidencia: drill inicial US3

| Campo | Resultado local |
| --- | --- |
| Fecha | 2026-07-29 |
| Fuente | namespace `primary` filesystem |
| Destino | namespace nueva `drill-001` |
| Alembic head | `0001_foundation_runtime` |
| RPO observado | 0 horas en fixture local |
| RTO objetivo | <= 4 horas |
| Datos de producto | ninguno; fixture sintético |

El test focal `tests/integration/recovery/test_backup_restore.py` crea un
objeto sintético y un dump lógico, genera un manifiesto firmado por checksum,
restaura beside-primary y verifica ambos hashes. La ejecución local dura menos
de un segundo para el fixture. No se declara evidencia de PostgreSQL, R2 o
MinIO reales: requiere Docker, servicios y credenciales disponibles.
