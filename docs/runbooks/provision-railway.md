# Aprovisionamiento del preview Railway

## Alcance y responsables

La persona operadora de plataforma ejecuta este procedimiento una vez y luego
cada release se promueve por pipeline. El preview consolidado usa Railway para
Postgres, Redis, un único bucket S3 y las cuatro superficies (web, api, worker,
scheduler); Supabase queda como proveedor de auth y Resend como proveedor de
correo. El manifiesto de release se entrega a las imágenes como JSON inline
(`UMBRAL_RELEASE_MANIFEST`) y lo setea el propio promote.

## Requisitos previos

- Cuenta Railway (plan Hobby) con acceso al proyecto `umbral-beta`.
- Proyecto Supabase `bpwgyvetbneghrtxcadm` con `SUPABASE_URL`
  (`https://bpwgyvetbneghrtxcadm.supabase.co`) y service role key
  (`sb_secret_...`).
- Cuenta Resend con un dominio verificado y un sender autorizado.
- Endpoint OTLP (Grafana Cloud) y proyecto Sentry para telemetría.

## Paso 1: repo secret `GHCR_DEPLOY_TOKEN`

1. Crear un classic PAT con scope `write:packages`, cuenta `tdalverme`; guardarlo
   en un gestor de secrets. Un fine-grained token sin `packages` alcanza el repo
   pero no publica imágenes GHCR.
2. En `github.com/tdalverme/umbral` → Settings → Secrets and variables →
   Actions → New repository secret `GHCR_DEPLOY_TOKEN`.
3. Verificar que aparezca en la lista; `release.yml` hace fail-fast si el secret
   falta o queda vacío al momento del tag.

## Paso 2: provisionamiento Railway

1. Crear el proyecto `umbral-beta` y el environment `preview`.
2. Agregar Postgres (template, URL única con PostGIS/pgvector), Redis y Object
   Storage (un solo bucket privado). Migrar a Neon después implica cambiar sólo
   `DATABASE_URL`; el diseño no exige `DATABASE_MIGRATION_URL` ni aislamiento
   primary/recovery.
3. Crear cuatro servicios desde imágenes GHCR (`ghcr.io/tdalverme/umbral/web` y
   `.../runtime`) y configurar por servicio: start commands, puerto público,
   healthcheck, restart, sleep y cron del scheduler según el diseño
   (`infra/railway/variables.example.json` y `src/umbral/infrastructure/config/settings.py`).
4. Cargar las variables estáticas por servicio:
   - `web`: `UMBRAL_PRIVATE_API_URL`, `UMBRAL_BFF_TOKEN`, access/session,
     `UMBRAL_RELEASE_ID`.
   - `api`: `DATABASE_URL`, `REDIS_URL`, `OBJECT_STORE_*`, proveedores,
     telemetría, `UMBRAL_API_BASE_URL`, `IDENTITY_*`, `EMAIL_*`.
   - `worker`/`scheduler`: igual que api (sin `IDENTITY_ISSUER`/capture).
   - En preview: `UMBRAL_ENV=preview`, `IDENTITY_PROVIDER=supabase`,
     `EMAIL_PROVIDER=resend`, `IDENTITY_ISSUER=<SUPABASE_URL>/auth/v1`,
     `IDENTITY_CAPTURE_ORIGIN=<dominio web>` y
     `UMBRAL_RELEASE_DIGEST=sha256:` + 64 hex son obligatorios.
   - `UMBRAL_RELEASE_ID`, `UMBRAL_RELEASE_DIGEST` y `UMBRAL_RELEASE_MANIFEST`
     los escribe el promote en cada release (`set-railway-images.ps1`); no hace
     falta provisionarlos a mano.
5. En Supabase: configurar Site URL y el redirect `/auth/capture`; en Resend:
   verificar el sender y registrar el webhook firmado.
6. Cargar los repo/environment secrets de Actions que consume `promote.yml` y el
   gate de dependencias. Variables requeridas y su fuente:
   - `RAILWAY_TOKEN`, `RAILWAY_API_TOKEN`: tokens sellados del proyecto/cuenta.
   - `DATABASE_URL`, `REDIS_URL`, `OBJECT_STORE_BUCKET`, `OBJECT_STORE_ENDPOINT_URL`,
     `OBJECT_STORE_ACCESS_KEY`, `OBJECT_STORE_SECRET_KEY`: valores de Railway.
   - `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `IDENTITY_ISSUER`: proyecto Supabase.
   - `RESEND_API_KEY`, `RESEND_FROM_EMAIL`: Resend.
   - `UMBRAL_PREVIEW_BASE_URL`: dominio público del servicio web.
   - `OTEL_EXPORTER_OTLP_ENDPOINT` y `OTEL_EXPORTER_OTLP_HEADERS`
     (`Authorization=Basic <base64(instanceId:token)>`): Grafana Cloud.
   - `SENTRY_DSN`: proyecto Sentry → Client Keys (DSN `https://...@....ingest.sentry.io/<id>`).
   - `UMBRAL_SMOKE_INVITEE`: un correo real y controlado por la persona operadora
     (recibe el magic-link del smoke).
   - `GHCR_DEPLOY_TOKEN`: ver Paso 1.
   Los endpoints de OTLP/Sentry/Supabase/Resend deben ser reales: el gate de
   dependencias hace probes HTTP en promote.

## Paso 3: release y promote

1. Llevar el incremento a la rama por defecto (`main`), porque el `promote`
   (workflow_dispatch) se lee desde `main` y su checkout descarga los scripts de
   ahí:
   `git checkout main; git merge --ff-only <rama>` y `git push origin main`.
2. Taggear el commit más reciente de `main` con el fix del manifest inline y el
   workflow `release` desbloqueado (sin `if` de secrets a nivel step):
   `git tag v0.2.1 <sha-de-main>` y `git push origin v0.2.1`.
3. Verificar la corrida `release` en Acciones: login GHCR con `GHCR_DEPLOY_TOKEN`,
   build de web/runtime `linux/amd64`, escribir `release-manifest.json` + `.sha256`
   y publicar el artifact `release-manifest-<sha>`.
4. **Visibilidad pública de los packages GHCR (una vez, web UI):** Railway (plan
   Hobby, pull anónimo) no soporta credenciales de registry privado, así que
   `ghcr.io/tdalverme/umbral/{runtime,web}` deben ser `public`. GitHub no expone
   API para cambiar visibilidad; hacerlo manual en
   https://github.com/users/tdalverme/packages/container/package/umbral%2Fruntime/settings
   (ídem `umbral%2Fweb`). El gate "Ensure GHCR packages are public" del release
   falla con el URL exacto si alguno quedó `private`.
5. Disparar `promote` (workflow_dispatch) con:
   - `manifest`: nombre del artifact (`release-manifest-<sha>`);
   - `release_run_id`: run ID de la corrida release;
   - `environment`: `preview`.
 6. Orden del promote: verify-access → validate-railway-config → backup →
    migrate (Alembic) → check-dependencies → set-railway-images (fija imagen y
    las `UMBRAL_RELEASE_*` por servicio) → wait-railway-services →
    preload de invitación → smoke de 15 escenarios. El smoke cierra SC-001.

## Servicio adicional: modelo gestionado (wrapper)

El chat en produccion consume el endpoint gestionado propio (ADR 0001):
`src/umbral/infrastructure/agent/model_gateway/server.py`. Se provisiona como
un servicio Railway `pserv` adicional (nombre `model`) desde la imagen runtime:

- Imagen: `ghcr.io/tdalverme/umbral/runtime:<sha>` (publica, igual que web/runtime).
- Start command: `python -m uvicorn umbral.infrastructure.agent.model_gateway.server:app --host 0.0.0.0 --port 8010`
- Variables: `PORT=8010`, `MODEL_GATEWAY_OPENAI_API_KEY=<OpenAI key>`,
  `MODEL_GATEWAY_SHARED_KEY=<misma que AGENT_MANAGED_API_KEY>`, y el healthcheck
  apuntando a `/openapi.json`.
- `AGENT_MANAGED_ENDPOINT` en api/worker/scheduler apunta a
  `http://model.<railway-internal-domain>:8010/v1/structured` (o al dominio
  publico del servicio si el acceso interno no aplica).

## Secrets de Actions adicionales (ademas de los 19 del Paso 2)

El promote tambien lee estos secrets para cablear el chat real, las alertas y
el wrapper (el smoke valida el chat con el modelo real):

- `AGENT_MODEL_PROVIDER` (`managed`), `AGENT_MODEL_NAME` (`gpt-4.1-mini`),
  `AGENT_MODEL_TIMEOUT_SECONDS` (30), `AGENT_MODEL_MAX_RETRIES` (2),
  `AGENT_MANAGED_ENDPOINT` (URL del servicio `model`),
  `AGENT_MANAGED_API_KEY` (misma que `MODEL_GATEWAY_SHARED_KEY`),
  `AGENT_GRAPH_RELEASE_ID` (`graph-release-005`) y
  `AGENT_V5_ACTIVATION_EVIDENCE` (referencia al reporte de evaluación aprobado).
- `NOTIFICATIONS_ENABLED` (true), `NOTIFICATIONS_POLICY_VERSION`
  (`notification-policy-v1`), `NOTIFICATIONS_PLANNER_DATASET_VERSION`
  (`planner-golden-v1`), `NOTIFICATIONS_EMAIL_FROM`, `NOTIFICATIONS_UNSUBSCRIBE_TTL_HOURS`,
  `NOTIFICATIONS_DEFAULT_TIMEZONE` (`America/Argentina/Buenos_Aires`).
- `MODEL_GATEWAY_OPENAI_API_KEY` y `MODEL_GATEWAY_SHARED_KEY` se cargan en el
  servicio `model` (provision manual; no via promote).
- `UMBRAL_SMOKE_INVITEE` debe ser un correo real y controlado: el smoke del
  chat requiere el magic-link real y ahora tambien entrega una notificacion
  de prueba si el radar tiene matches publicados.

## Verificación y compensación

- El runtime valida el manifiesto inline contra el contrato versionado y reporta
  su `manifest_sha256`; debe coincidir con el `.sha256` del artifact.
- Ante un smoke fallido, ver `release-rollback.md`: volver al snapshot anterior
  sólo si el schema es compatible.
