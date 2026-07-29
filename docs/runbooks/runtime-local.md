# Recorrido local del runtime

Este recorrido valida el slice `foundation-runtime` desde un checkout local.
Requiere Python 3.13, Node 24.15.0/npm 12.0.1 y las dependencias instaladas
con los lockfiles. No levanta PostgreSQL, Redis ni MinIO para las pruebas de
contrato; las probes de infraestructura fallan cerrado si esos servicios no
están disponibles.

## Comandos

Desde la raíz del repositorio:

```powershell
.venv\Scripts\Activate.ps1
.\scripts\check.ps1
.\scripts\check-contracts.ps1
.\scripts\check-migrations.ps1
.\scripts\check-api.ps1
npm.cmd run api:check --workspace @umbral/web
```

El harness ejecuta Ruff, mypy, pytest, arquitectura, migraciones, drift de
OpenAPI/client, ESLint, TypeScript, Vitest y la colección Playwright. Para
probar el cliente en un host con varios Node instalados, `NPM_EXECUTABLE` puede
apuntar al `npm.cmd` de npm 12; en un checkout normal basta con tener Node 24 y
npm 12 en `PATH`.

## Identidad observada

Para una ejecución reproducible, configurar `UMBRAL_RELEASE_MANIFEST` y las
variables de entorno del ejemplo con el mismo manifiesto validado. El API y
las rutas web deben devolver el mismo `release_id`, `git_sha`, `artifact_digest`
y `contract_major`; el manifiesto local de referencia es
`tests/fixtures/release-manifests/valid.json`.

La liveness `/health` no consulta dependencias ni escribe estado. `/ready` y
`/version` sólo leen configuración/manifiesto, responden `Cache-Control:
no-store` y devuelven request/correlation IDs en el API.

## Resultado y límites

Guardar el resultado cronometrado y el release observado en
`docs/runbooks/evidence/us1-local-start.md`. Si no hay Docker, registrar la
omisión en vez de crear servicios simulados: la verificación de esquema
PostgreSQL/PostGIS/pgvector queda pendiente para el entorno con `DATABASE_URL`.
