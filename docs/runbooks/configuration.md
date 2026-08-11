# Configuraci\u00f3n de runtime

La configuraci\u00f3n se inyecta al iniciar cada superficie; nunca se incluye en
la imagen ni se imprime en diagn\u00f3sticos. `Settings.from_environment` acepta
s\u00f3lo este inventario y sus fallos exponen exclusivamente `rule_code` y
`field_name`.

| Variable | Owner | Fuente | Consumidor | Obligatoria | Formato/validaci\u00f3n | Secreto | Exposici\u00f3n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `UMBRAL_ENV` | Plataforma | entorno de deployment | API, worker, scheduler, web server | S\u00ed | `local`, `preview` o `production` | No | logs metadata permitidos |
| `UMBRAL_RELEASE_ID` | Release engineering | manifiesto promovido | cuatro superficies | S\u00ed | identificador de release | No | `/version`, metadata |
| `UMBRAL_RELEASE_MANIFEST` | Release engineering | pipeline/local file | cuatro superficies | S\u00ed | JSON inline en preview (seteado por el pipeline) o path local legible | No | no exponer path |
| `UMBRAL_RELEASE_DIGEST` | Release engineering | entorno de deployment | API, worker, scheduler, web server | Preview/production | `sha256:` + 64 hex | No | metadata permitida |
| `DATABASE_URL` | Plataforma | secret store/Compose local | API, worker, scheduler | S\u00ed | PostgreSQL URL; TLS y host no local fuera de local | S\u00ed | nunca |
| `REDIS_URL` | Plataforma | secret store/Compose local | API, worker, scheduler | S\u00ed | Redis URL; `rediss` fuera de local | S\u00ed | nunca |
| `OBJECT_STORE_BACKEND` | Plataforma | entorno de deployment | API, worker | S\u00ed | `filesystem` s\u00f3lo local; `s3` fuera de local | No | metadata permitida |
| `OBJECT_STORE_ROOT` | Plataforma | entorno local | API, worker | Si usa filesystem | path local | No | nunca |
| `OBJECT_STORE_BUCKET` | Plataforma | secret store/Compose local | API, worker | Si usa s3 | bucket privado | No | nunca |
| `OBJECT_STORE_ENDPOINT_URL` | Plataforma | secret store/Compose local | API, worker | Si usa s3 | URL HTTPS fuera de local | No | nunca |
| `OBJECT_STORE_ACCESS_KEY` | Plataforma | secret store/Compose local | API, worker | Si usa s3 | credencial del proveedor | Sí | nunca |
| `OBJECT_STORE_SECRET_KEY` | Plataforma | secret store/Compose local | API, worker | Si usa s3 | credencial del proveedor | Sí | nunca |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Observabilidad | entorno de deployment | API, worker, scheduler, web server | S\u00ed | URL; HTTPS fuera de local | No | no exponer host |
| `SENTRY_DSN` | Observabilidad | secret store | API, worker, scheduler, web server | Preview/production | HTTPS DSN no vac\u00edo | S\u00ed | nunca |
| `UMBRAL_API_BASE_URL` | Plataforma | runtime server environment | web server | S\u00ed | URL privada HTTPS fuera de local | No | nunca al browser |
| `UMBRAL_ACCESS_AUDIENCE` | Seguridad | secret store | web server/API access boundary | Preview/production | audience no vac\u00eda | S\u00ed | nunca |

`NEXT_PUBLIC_*` no tiene valores aprobados en este incremento. Agregar uno
requiere revisar que sea no secreto, estable entre ambientes y necesario en el
browser; hosts privados y credenciales permanecen configuraci\u00f3n de servidor.

Los archivos `.env.example` contienen exclusivamente valores locales de ejemplo.
No se copian a preview ni producci\u00f3n.

En preview, `UMBRAL_RELEASE_ID`, `UMBRAL_RELEASE_DIGEST` y
`UMBRAL_RELEASE_MANIFEST` (JSON inline) los escribe el pipeline en cada promote;
ver `provision-railway.md`.

## Endpoint gestionado de modelo (ADR 0001)

El `ManagedModelGateway` cliente (`AGENT_MODEL_PROVIDER=managed`) consume un
endpoint propio separado del producto: `src/umbral/infrastructure/agent/
model_gateway/server.py`. Se ejecuta como servicio independiente:

```powershell
$env:MODEL_GATEWAY_OPENAI_API_KEY = 'sk-...'   # API key del proveedor (OpenAI)
$env:MODEL_GATEWAY_SHARED_KEY = '...'           # opcional; si se fija, la API debe
                                                # enviarla como AGENT_MANAGED_API_KEY
uvicorn umbral.infrastructure.agent.model_gateway.server:app --port 8010
```

Contrato: `POST /v1/structured` recibe `{model, model_version, prompt_version,
schema_version, schema, messages}` y responde `{content, usage}`; llama al
provider con output JSON estructurado y corrige una vez respuestas no JSON.

Variables del agente en Umbral: `AGENT_MODEL_PROVIDER=managed`,
`AGENT_MANAGED_ENDPOINT=http://127.0.0.1:8010/v1/structured`,
`AGENT_MANAGED_API_KEY`, `AGENT_MODEL_NAME=gpt-4.1-mini`.

Evals con el proveedor real (opt-in, fuera de CI, requiere Postgres migrado):

```powershell
.\scripts\run-real-evals.ps1 -CaseLimit 1 -CostCapUsd 1   # smoke
.\scripts\run-real-evals.ps1 -CostCapUsd 2                # dataset completo
```

El flow falla con exit code != 0 si cualquier caso no cumple las cinco senales
deterministas; el resumen por caso se imprime en el JSON de salida. La eleccion
del modelo concreto es un parametro de release (graph-releases-v1) evaluable y
revertible.
