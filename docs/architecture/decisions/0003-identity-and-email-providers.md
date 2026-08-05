# ADR 0003: identidad y correo de la beta privada

Estado: aceptado · Fecha: 2026-07-29 · Owner: Product Engineering

Umbral usa Supabase Auth sólo como prueba externa de email y Resend sólo como
entrega transaccional. Invitaciones, usuarios, roles, sesiones, intentos y
auditoría viven en PostgreSQL de Umbral. El navegador nunca recibe credenciales
de proveedor ni una sesión Supabase.

| Criterio | Decisión | Riesgo y mitigación |
| --- | --- | --- |
| Magic link y expiración | Supabase `generate_link`, 15 minutos | SDK/shape cambiante; adapter y conformance en preview |
| Entrega e idempotencia | Resend API con `identity.magic-link/{attempt_id}` | outage; issue job falla cerrado y permite solicitar otro enlace |
| Local/test | fakes determinísticos y Recording/Mailpit | no prueba disponibilidad real; smoke preview obligatorio |
| Datos | PostgreSQL privado de Umbral | requiere migración/backup; provider no tiene tablas de producto |
| Salida | exportar subject/email y reconstruir links en otro adapter | issuer/link conflict; no se fusionan usuarios por email |

Credenciales, issuers, dominios y destinos se separan por test, local, preview
y producción. Sólo el API/worker puede leer secretos. La operación de salida
deshabilita el provider en configuración, conserva los objetos locales y
ejecuta conformance antes de cambiar el registro activo.

## Evidencia de verificación

Registro de verificación del incremento `private-beta-identity` (2026-08-04,
rama `codex/private-beta-identity-deployment`). Todas las suites se ejecutaron
con `PYTHONPATH=src` y el entorno `.venv` del worktree.

**SC-007 (registro de decisión).** La suite `tests/contract/test_provider_decision_record.py`
comprueba que este documento cubre los criterios operativos obligatorios de
UM-H1-023 (magic link, idempotencia, local/test, PostgreSQL, salida, preview,
credenciales e issuer). Resultado: 1 test, en verde.

**SC-006 (fallos de proveedor no conceden acceso).** La suite
`tests/integration/identity/test_provider_failures.py` simula indisponibilidad
o rechazo en generación, envío, verificación y revocación; en cada caso no se
crea usuario, vínculo ni sesión y el intento queda en `failed` o `issued` sin
mutación local. Resultado: 4 tests, en verde. El aislamiento por ambiente
(`tests/integration/identity/test_environment_isolation.py`) y la readiness
degradada (`tests/unit/runtime/test_identity_readiness.py`,
`tests/integration/runtime/test_readiness_failure_isolation.py`) refuerzan que
un proveedor de otro ambiente o una falla no degradan la readiness de producto.

Cualquier reemplazo de proveedor mantiene esta sección actualizada y vuelve a
ejecutar SC-006 y SC-007 antes de promocionar a producción.
