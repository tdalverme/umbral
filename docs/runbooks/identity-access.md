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
