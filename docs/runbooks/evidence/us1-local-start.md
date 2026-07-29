# Evidencia US1 — inicio local

Fecha de ejecución: 2026-07-29 (America/Argentina/Buenos_Aires)

## Release y configuración

- Manifiesto: `tests/fixtures/release-manifests/valid.json`.
- `release_id`: `foundation-20260101`.
- `git_sha`: `0123456789abcdef0123456789abcdef01234567`.
- `artifact_digest`: `sha256:1111111111111111111111111111111111111111111111111111111111111111`.
- `contract_major`: `1`.
- El recorrido API/web usa el mismo manifiesto; los defaults `foundation-local`
  sólo se usan para que el proceso pueda iniciar sin configuración explícita.

## Checks ejecutados

| Check | Resultado |
| --- | --- |
| `scripts/check.ps1` con Node 24.15.0/npm 12.0.1 | PASS |
| Ruff, mypy estricto y pytest | PASS — 85 tests |
| Contratos OpenAPI 3.1, compatibilidad y client drift | PASS |
| Alembic head/metadata y SQL offline | PASS; drift live omitido sin `DATABASE_URL` |
| ESLint, TypeScript y Vitest | PASS — 12 tests |
| Colección Playwright | PASS — 6 tests enumerados |
| `/health`, `/ready`, `/version` API | PASS; no-store y sin efectos observables |
| Rutas web `/health`, `/ready`, `/version` | PASS; manifiesto local y sin llamadas externas |

El recorrido completo terminó sin fallos bloqueantes. No se ejecutó un browser
real ni se iniciaron contenedores en este entorno; por eso las pruebas de
Playwright se dejaron recolectadas y la comprobación PostgreSQL/PostGIS/pgvector
se mantiene como gate del entorno con servicios.
