# Registro de aceptación de foundation-runtime

**Estado:** aceptado para cierre del incremento (gates locales en verde)

**Fecha:** 2026-07-29 (America/Argentina/Buenos_Aires)

**Rama/PR:** `001-foundation-runtime` / [PR #1](https://github.com/tdalverme/umbral/pull/1)

**Commit de implementación verificado:** `dbdd343`

**Alcance aceptado:** UM-H1-001 a UM-H1-012 y UM-H1-016 a UM-H1-020. Las
historias de identidad UM-H1-023 y UM-H1-013 a UM-H1-015 no forman parte de
este cierre.

## Evidencia por historia

| Historia | Evidencia principal | Resultado local |
| --- | --- | --- |
| US1 — UM-H1-001…006 | `docs/runbooks/evidence/us1-local-start.md`, arquitectura, OpenAPI, cliente generado y web | PASS |
| US2 — UM-H1-007…009 | `docs/runbooks/evidence/us2-data-evolution.md`, Alembic offline, metadata y conflictos optimistas | PASS; drift live requiere `DATABASE_URL` |
| US3 — UM-H1-010…012 | `scripts/check-jobs.ps1`, `scripts/check-storage.ps1`, `scripts/check-recovery.ps1`, `docs/runbooks/evidence/us3-restore-initial.md` | PASS local; proveedores reales requieren servicios/credenciales |
| US4 — UM-H1-016…020 | señales metadata-only, readiness, manifest, access, promoción/rollback y `docs/runbooks/evidence/us4-*.md` | PASS local; drills remotos pendientes |

## Verificación de aceptación

| Gate | Resultado observado |
| --- | --- |
| Harness `scripts/check.ps1` | PASS; 146 tests Python, Ruff, mypy, arquitectura, API, migraciones offline, jobs, objetos, recovery, release y web |
| Web | PASS; OpenAPI generado sin diff, ESLint, TypeScript, 13 tests Vitest y 6 casos Playwright recolectados |
| Build | PASS con Next 16.2.12 y salida `.next/standalone`; warning NFT dinámico documentado |
| Backlog | PASS; 17 IDs del alcance marcados `[x]`; UM-H1-013…015 y UM-H1-023 permanecen `[ ]` |
| Seguridad operativa | PASS local; acceso fail-closed, logs metadata-only y sin secretos en evidencia |

## Decisión y límites

El incremento se considera cerrado para desarrollo local y revisión del PR. La
aceptación no afirma que exista una provisión remota: el drift live de
PostgreSQL, MinIO/Redis reales, Render, Cloudflare Access, R2, Grafana y Sentry
requiere servicios, proyectos y credenciales explícitos. El único `SKIP`
esperado del harness en este host es Spec Kit sin `specify.exe` y el drift live
sin `DATABASE_URL`; ambos están documentados y no ocultan una superficie local.

## Siguiente incremento desbloqueado

El siguiente incremento recomendado es **`private-beta-identity`**, compuesto
por UM-H1-023 y UM-H1-013 a UM-H1-015:

1. seleccionar providers de identidad/email y registrar el ADR de salida;
2. implementar invitaciones y magic links de un uso y con expiración;
3. mapear la identidad externa a usuarios de producto;
4. aplicar roles mínimos con autorización deny-by-default.

`foundation-runtime` deja disponibles configuración por ambiente, persistencia,
auditoría, correlación, probes, delivery y recovery para que ese incremento se
construya sin reabrir el alcance de esta rama. Los incrementos de importación y
radar permanecen bloqueados por identidad y se retoman después de ese cierre.
