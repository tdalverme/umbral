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
6. Cargar los repo secrets de Actions que consume `promote.yml` y el gate de
   dependencias. Los 19 requeridos y su fuente:
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
2. Taggear el commit más reciente de `main` que contiene el fix del manifest
   inline (hoy `87f8167`):
   `git tag v0.2.1 87f8167` y `git push origin v0.2.1`.
3. Verificar la corrida `release` en Acciones: login GHCR con `GHCR_DEPLOY_TOKEN`,
   build de web/runtime `linux/amd64`, escribir `release-manifest.json` + `.sha256`
   y publicar el artifact `release-manifest-<sha>`.
4. Disparar `promote` (workflow_dispatch) con:
   - `manifest`: nombre del artifact (`release-manifest-<sha>`);
   - `release_run_id`: run ID de la corrida release;
   - `environment`: `preview`.
5. Orden del promote: verify-access → validate-railway-config → backup →
   migrate (Alembic) → check-dependencies → set-railway-images (fija imagen y
   las `UMBRAL_RELEASE_*` por servicio) → wait-railway-services →
   preload de invitación → smoke de 15 escenarios. El smoke cierra SC-001.

## Verificación y compensación

- El runtime valida el manifiesto inline contra el contrato versionado y reporta
  su `manifest_sha256`; debe coincidir con el `.sha256` del artifact.
- Ante un smoke fallido, ver `release-rollback.md`: volver al snapshot anterior
  sólo si el schema es compatible.
