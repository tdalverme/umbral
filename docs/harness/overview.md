# Harness de desarrollo

El harness es el loop local de feedback para personas y agentes. Su objetivo
es detectar cambios incompatibles con la documentacion y la arquitectura antes
de empezar el desarrollo funcional, sin convertir la V1 en una plataforma de
CI.

## Punto de entrada

Desde la raiz del repo:

```powershell
.\scripts\check.ps1
```

El comando devuelve codigo `0` si no hay fallos bloqueantes y `1` si falla un
check requerido. Cada resultado se marca como `PASS`, `FAIL` o `SKIP`.

## Checks actuales

| Check | Cuando corre | Que protege |
| --- | --- | --- |
| Documentacion | Siempre | Archivos requeridos, limite de `AGENTS.md`, placeholders de la constitucion y tabla de endpoints. |
| Arquitectura | Cuando existe `src/umbral` o `umbral` | Imports prohibidos desde dominio, aplicacion y agent. |
| Spec Kit | Si existe `.venv/Scripts/specify.exe` | Estado de la instalacion e integraciones; en este host queda como prerrequisito ausente. |
| API | Cuando existe `umbral.api.main` | Import de la app y presencia de `/health` en OpenAPI. |
| Migraciones | Cuando existe Alembic | Snapshot offline, downgrade empty-only y drift live si hay `DATABASE_URL`. |
| Jobs | Cuando existe `application/jobs` | Contratos, cola JSON, idempotencia, leases, scheduler y worker. |
| Objetos | Cuando existe `application/objects` | Conformance filesystem/S3 fake y versiones exactas. |
| Recuperación | Cuando existe `ops/backup.py` | Manifest, checksums, restore beside-primary y RPO/RTO. |
| Release | Cuando existe manifest schema | Manifest, access policy, lock y gates locales. |
| Web | Cuando existe `apps/web` | Cliente OpenAPI, lint, TypeScript, Vitest y colección Playwright. |
| Tests | Cuando hay `.py` bajo `tests/` | Suite automatizada mediante `pytest`. |

El único `SKIP` esperado en este checkout es Spec Kit sin el ejecutable local y
el drift live de PostgreSQL sin `DATABASE_URL`; ambos son prerrequisitos
documentados, no superficies silenciosamente omitidas. Docker, MinIO, Render,
Cloudflare y R2 requieren servicios/credenciales explícitos.

## Regla de crecimiento

Agregar un check solo cuando exista una regresion concreta que pueda detectar
de forma mecanica. Cada check debe tener una salida accionable y una razon
clara para ser requerido, opcional o salteable. No agregar Docker, CI complejo,
hooks, browser automation ni observabilidad operativa hasta que el producto
tenga una superficie que los necesite.
