# Configuraci\u00f3n de runtime

La configuraci\u00f3n se inyecta al iniciar cada superficie; nunca se incluye en
la imagen ni se imprime en diagn\u00f3sticos. `Settings.from_environment` acepta
s\u00f3lo este inventario y sus fallos exponen exclusivamente `rule_code` y
`field_name`.

| Variable | Owner | Fuente | Consumidor | Obligatoria | Formato/validaci\u00f3n | Secreto | Exposici\u00f3n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `UMBRAL_ENV` | Plataforma | entorno de deployment | API, worker, scheduler, web server | S\u00ed | `local`, `preview` o `production` | No | logs metadata permitidos |
| `UMBRAL_RELEASE_ID` | Release engineering | manifiesto promovido | cuatro superficies | S\u00ed | identificador de release | No | `/version`, metadata |
| `UMBRAL_RELEASE_MANIFEST` | Release engineering | secret mount/local file | cuatro superficies | S\u00ed | path local legible | No | no exponer path |
| `UMBRAL_RELEASE_DIGEST` | Release engineering | entorno de deployment | API, worker, scheduler, web server | Preview/production | `sha256:` + 64 hex | No | metadata permitida |
| `DATABASE_URL` | Plataforma | secret store/Compose local | API, worker, scheduler | S\u00ed | PostgreSQL URL; TLS y host no local fuera de local | S\u00ed | nunca |
| `REDIS_URL` | Plataforma | secret store/Compose local | API, worker, scheduler | S\u00ed | Redis URL; `rediss` fuera de local | S\u00ed | nunca |
| `OBJECT_STORE_BACKEND` | Plataforma | entorno de deployment | API, worker | S\u00ed | `filesystem` s\u00f3lo local; `s3` fuera de local | No | metadata permitida |
| `OBJECT_STORE_ROOT` | Plataforma | entorno local | API, worker | Si usa filesystem | path local | No | nunca |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Observabilidad | entorno de deployment | API, worker, scheduler, web server | S\u00ed | URL; HTTPS fuera de local | No | no exponer host |
| `SENTRY_DSN` | Observabilidad | secret store | API, worker, scheduler, web server | Preview/production | HTTPS DSN no vac\u00edo | S\u00ed | nunca |
| `UMBRAL_API_BASE_URL` | Plataforma | runtime server environment | web server | S\u00ed | URL privada HTTPS fuera de local | No | nunca al browser |
| `UMBRAL_ACCESS_AUDIENCE` | Seguridad | secret store | web server/API access boundary | Preview/production | audience no vac\u00eda | S\u00ed | nunca |

`NEXT_PUBLIC_*` no tiene valores aprobados en este incremento. Agregar uno
requiere revisar que sea no secreto, estable entre ambientes y necesario en el
browser; hosts privados y credenciales permanecen configuraci\u00f3n de servidor.

Los archivos `.env.example` contienen exclusivamente valores locales de ejemplo.
No se copian a preview ni producci\u00f3n.
