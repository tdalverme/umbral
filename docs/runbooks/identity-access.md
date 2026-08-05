# Operación de acceso de beta privada

## Local

1. `docker compose up postgres redis mailpit`.
2. Precargar una invitación desde una composición controlada:
   `AccessAdministration.preload_invitation("persona@example.com")`.
3. Ejecutar el API y solicitar `POST /api/v1/auth/magic-link-requests` con el
   BFF token. El mensaje visible siempre es neutral.
4. El worker procesa sólo el UUID del intento; el enlace se inspecciona en
   Recording/Mailpit y se confirma mediante `GET /auth/capture` y el POST
   explícito de `/auth/confirm`.

## Transición de ingress

1. Antes de publicar, ejecutar `scripts/deploy/verify-access.ps1` y el smoke
   del manifiesto exacto; el origen Render permanece cerrado y la sesión de
   Umbral protege las rutas de producto.
2. En preview puede mantenerse Cloudflare Access como capa adicional. En
   producción, retirar sólo la exigencia de JWT de Cloudflare después de que
   login, captura, no-invitado, logout, idle y rollback hayan pasado.
3. Para rollback, restaurar el manifiesto anterior, reactivar la política de
   acceso temporal y deshabilitar el proveedor de login; nunca borrar usuarios,
   vínculos, roles ni auditoría de Umbral.

## Incidentes

- provider indisponible: no se crea sesión/usuario; revisar `issue_failed` y
  permitir un nuevo pedido;
- conflictos de subject/email: conservar estado y escalar a operación;
- sesión idle: la siguiente operación devuelve `auth.session_required`; no se
  renueva desde rutas públicas o denegadas;
- fingerprints de solicitudes se purgan a las 24 horas.

No copiar tokens, cookies, URLs completas, emails ni cuerpos de webhook en
logs, tickets o evidencia.

## Evidencia de aceptación SC-001–SC-010

Matriz de evidencia del incremento `private-beta-identity`, registrada el
2026-08-04 en la rama `codex/private-beta-identity-deployment`. Estado
`verificado` indica suites re-ejecutadas en esta sesión; `registrado` indica
corridas previas documentadas en el ledger SDD (ver `.superpowers/sdd/
2026-08-01-private-beta-identity-deployment/progress.md` y task-*-report.md).

| SC | Criterio | Evidencia | Estado |
| --- | --- | --- | --- |
| SC-001 | 20 viajes de primer acceso <3 min | `tests/e2e/identity.spec.ts` (7 escenarios, 1 worker) | 7 escenarios verificados (2026-08-04); 20 viajes cronometrados pendientes en preview |
| SC-002 | 100% corpus no-invitado/deshabilitado/vencido/reutilizado/reemplazado/alterado rechazado sin revelar membresía | unit `test_link_state.py`, `test_access_flow.py`; contract `test_identity_provider.py`; e2e login/capture/expired | verificado (80 regresión + 7 e2e) |
| SC-003 | 100% matriz identidad/estado/rol/ownership deny-by-default, cero cross-user | unit `test_policy.py`; integración `test_authorization_matrix.py` | verificado (unit + 22 PostgreSQL) |
| SC-004 | 10 duplicados → máximo 1 consumo/usuario/vínculo/sesión | integración `test_magic_link_flow.py::test_ten_duplicate_confirmations_create_one_session`; conformance `test_concurrent_confirmation_consumes_one_attempt_once` | verificado real-Postgres (2026-08-04) |
| SC-005 | 100% eventos correlacionados; cero tokens/enlaces/credenciales en diagnósticos | unit `test_redaction.py`; contract `test_identity_redaction.py`; smoke scenario `redaction` | verificado (80 + 13 + 22) |
| SC-006 | 100% sims de indisponibilidad/rechazo → cero sesiones/vínculos/usuarios | `tests/integration/identity/test_provider_failures.py` (4) + readiness | verificado (10) |
| SC-007 | registro de decisión cubre 100% criterios UM-H1-023 + riesgos aceptados | `tests/contract/test_provider_decision_record.py` + ADR 0003 §Evidencia | verificado |
| SC-008 | acceso válido repetido → mismo usuario, sin duplicados ni fusión | unit `test_access_flow.py::test_repeat_magic_link_reuses_same_product_identity`; integración `test_magic_link_flow.py::test_repeat_login_reuses_identity_and_creates_a_new_session` | verificado (unit + 22 PostgreSQL) |
| SC-009 | 7 días idle: activa permanece; idle completa exige nuevo link | conformance `test_authorization_activity_and_audit_commit_and_rollback_together`; `test_authorization_matrix.py` | verificado real-Postgres (2026-08-04) |
| SC-010 | 4º por email / 21º por origen: cero emisiones/invalidaciones, neutral, vuelve a admitir | unit `test_rate_limit.py`; conformance `test_rate_limit_serializes_concurrent_requests_and_report_restarts` | verificado (unit + real-Postgres) |

Corridas de referencia registradas: `23 passed` de la suite PostgreSQL de
identidad (store conformance, webhook dedupe, magic-link flow, export) en el
reporte task-5; 45 tests de composición/identidad en task 8; 21 de
provider-conformance/recovery en task 13. El smoke de release local
(`scripts/deploy/smoke.ps1 -Mode local` sobre un manifiesto válido) responde
`identity_smoke: accepted` con las ocho superficies y cero datos de producto.

## Límites conocidos de proveedor

- Supabase `generate_link`: expiración máxima del OTP/magic-link de 900
  segundos; sólo el redirect del ambiente está permitido en el allowlist;
  sin signup abierto ni claves de browser expuestas.
- Resend: el dominio/test mode no puede enviar como producción; click/open
  tracking desactivado; webhook firmado y deduplicado por evento del proveedor.
- Cambiar la vigencia de 15 minutos del enlace requiere evidencia y una
  actualización explícita de la especificación; no se extiende por decisión de
  runtime.
- En pruebas locales, fakes determinísticos y Mailpit no prueban disponibilidad
  real: el smoke de preview es obligatorio antes de promocionar.

## Follow-ups operativos pendientes

- Re-ejecutar el smoke de preview contra el manifiesto exacto
  (`scripts/deploy/smoke.ps1 -Mode preview -BaseUrl <origin>`), que requiere
  preview desplegado, `UMBRAL_SMOKE_INVITEE`,
  `UMBRAL_SMOKE_OPERATOR_DATABASE_URL` y token de observación Resend. El commit
  `49a7c6e` ejecutó la corrida real el 2026-08-01; el worktree extiende el smoke
  a 15 escenarios y necesita una nueva corrida para cerrar SC-001 y el
  manifiesto vigente.
- Medir el rollback de producción <15 min; `docs/runbooks/evidence/
  us4-production-rollback.md` registra que no se ejecutó remotamente.
- Alinear `docs/runbooks/evidence/us4-preview-release.md` con la plataforma
  real (Railway consolidado); el documento aún cita Render/Cloudflare de la
  topología de diseño.
- Corregir `compose.yaml` local: pglayers rechaza `POSTGRES_PASSWORD=umbral_local_only`
  por contener el username (`umbral`); el quickstart local depende de este
  servicio. Las suites de prueba usan Testcontainers y no dependen de compose.
