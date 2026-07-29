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
