# Quickstart: Notificaciones y alertas proactivas (H5)

Guia de validacion end-to-end. Detalles de contratos en
[contracts/notifications-contracts-v1.md](./contracts/notifications-contracts-v1.md)
y de datos en [data-model.md](./data-model.md).

## Prerequisitos

- Entorno local del repo funcionando (Python 3.13 en `.venv`, Postgres via
  `docker compose up -d postgres`, migraciones al head).
- `EMAIL_PROVIDER=recording` (local) — los emails quedan en el fake y se
  verifican por evento, no por bandeja real.

## Comandos

```powershell
# 1. Migracion
$env:DATABASE_URL = 'postgresql://umbral:local_db_pass_01@localhost:5432/umbral'
.\.venv\Scripts\python.exe -m alembic upgrade head

# 2. Harness del incremento (contract + unit + integracion + migracion)
.\scripts\check-alerts.ps1

# 3. Harness completo del repo
.\scripts\check.ps1

# 4. Scheduler local (duties plan/digest + entrega)
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m umbral.workers scheduler

# 5. API de desarrollo
.\.venv\Scripts\python.exe -m uvicorn umbral.api.main:app --reload

# 6. Web
npm run dev --workspace @umbral/web
```

## Escenarios de validacion

1. **Planner golden**: `check-alerts.ps1` corre el gate del planner contra
   `contracts/notifications/v1/planner-golden-v1.json` (misma entrada ->
   misma decision y razon; 0 duplicados; quiet hours; fatiga; digest).
2. **Preferencias**: con sesion de usuario, `PUT /api/v1/notifications/
   preferences` valida timezone/quiet hours/umbral y devuelve la version
   nueva; la siguiente decision usa esa version (verificar en la tabla
   `notification_preferences` el bump).
3. **Decision real**: con un recommendation run publicado y el duty de plan
   ejecutado, aparece una fila en `notification_decisions` con trigger,
   reason_code y estado; 0 duplicados al repetir la pasada.
4. **Entrega**: el job `notifications.deliver` entrega con el adapter
   recording; el evento `notification.delivered.v1` registra el provider
   message id; al fallar el proveedor (simulado) el job reintenta y agota en
   dead-letter sin perder la decision.
5. **Quiet hours**: con quiet hours 22-08 y un item nuevo a las 23:00, la
   decision queda `postponed` con razon y se materializa al abrirse la
   ventana (duty de digest/reenvio).
6. **Cadencia hibrida**: un price drop (o new match con score sobre el
   umbral) se entrega inmediato; un new match de score bajo queda
   `pending_digest` y se agrupa en el digest de las 9:00.
7. **Inbox web**: el centro muestra las mismas decisiones que el email;
   marcar leida persiste `read_at` y emite `notification.viewed.v1`.
8. **Baja desde email**: el enlace de baja con token valido desactiva las
   preferencias sin login y emite `notification.unsubscribed.v1`; un token
   vencido o reutilizado es rechazado con `notifications.token_expired`.

## Resultados esperados

- Gate del planner golden: 100% de los casos verdes (determinista).
- 0 notificaciones duplicadas y 0 entregas fuera de quiet hours en los
  escenarios 3-5.
- Fallos de proveedor simulados: 0 perdidas y 0 duplicados (escenario 4).
- Todos los eventos `notification.*.v1` sin PII y con los campos del
  contrato.
