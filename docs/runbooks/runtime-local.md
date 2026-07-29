# Recorrido local del runtime

Este recorrido verifica el arranque independiente de la API y la web para
`foundation-runtime`. No crea búsquedas, listings, trabajos ni objetos; las
pruebas de API usan el `TestClient` y las pruebas web se limitan a contratos y
colección Playwright.

## Precondiciones

Ejecutar desde la raíz del repositorio con Python 3.13, Node.js 24.15.0 y npm
12.0.1. En el equipo usado para esta evidencia, los wrappers temporales de
Node/npm viven en `._tmp_npm12`; en una máquina con Node 24/npm 12 instalados
directamente no hace falta el prefijo de PATH.

```powershell
$env:PATH = (Join-Path (Get-Location) '._tmp_npm12') + ';' + $env:PATH
$env:NPM_EXECUTABLE = (Join-Path (Get-Location) '._tmp_npm12\npm.cmd')
node --version       # v24.15.0
npm.cmd --version    # 12.0.1
.\.venv\Scripts\python.exe --version  # Python 3.13.14
```

El recorrido local de la API usa el manifiesto sentinel `<local>` de la
composición (`release_id=foundation-local`, `database_revision=local` y
`manifest_sha256` de ceros). La validación de archivo y el cliente generado se
ejercitan además contra
`tests/fixtures/release-manifests/valid.json` (`foundation-20260101`,
SHA-256 `290498d58755176719c79661511e4430263c7d41dbfb24f14bfb92347c1e44fe`).

## Secuencia verificada

El recorrido cronometrado del 29 de julio de 2026 duró aproximadamente 2 min
15 s, incluyendo el harness completo y el build de producción con Node
24.15.0/npm 12.0.1. Los comandos fueron ejecutados en el orden siguiente.

### 1. Probes de API

```powershell
$env:PYTHONPATH = 'src'
@'
from fastapi.testclient import TestClient
from umbral.api.main import app

client = TestClient(app)
for path in ('/health', '/ready', '/version'):
    response = client.get(path)
    print(path, response.status_code, response.json())
'@ | .\.venv\Scripts\python.exe -
```

Resultado observado: `/health` y `/ready` devolvieron `200`, `/version`
devolvió `200`, todos con `Cache-Control: no-store`; el release observado fue
`foundation-local` y el cuerpo de health fue exactamente
`{"status":"alive"}`.

### 2. Contrato OpenAPI y cliente generado

```powershell
.\scripts\export-openapi.ps1 -OutputPath contracts\openapi\v1\openapi.json
.\scripts\check-contracts.ps1
npm.cmd run api:check --workspace @umbral/web
```

Los tres comandos terminaron con código `0`. La exportación y regeneración
fueron deterministas: Hey API `0.99.0` escribió cinco archivos y no quedó diff
en `apps/web/src/lib/api/generated`.

### 3. Gates Python

```powershell
.\scripts\check-python.ps1
```

Con `NPM_EXECUTABLE` apuntando al npm 12 del preámbulo, Ruff y mypy pasaron y
pytest terminó `146 passed` (tres warnings de dependencias, sin fallos). Sin
el override, este host resuelve el `npm.cmd` global de Node 22 y el caso del
cliente generado falla antes de ejecutar; no es una falla del contrato y debe
corregirse usando Node 24/npm 12.

### 4. Gates web

```powershell
.\scripts\check-web.ps1
npm.cmd run build --workspace @umbral/web
```

`check-web.ps1` pasó dependencias, cliente OpenAPI, ESLint, TypeScript, Vitest
(`13 passed`) y la colección Playwright (`6 tests` listados). El build Next
16.2.12 también terminó correctamente en aproximadamente 67 s y generó
`.next/standalone`; Turbopack informó únicamente el warning esperable de
trazado amplio por la lectura dinámica del manifiesto local.

## Brechas y límites del recorrido

- Playwright se verificó con `--list`; no se ejecutaron navegadores ni smoke
  E2E porque no se levantó un servidor web con un manifiesto de release montado.
  La evidencia E2E completa queda para el recorrido de despliegue.
- `docker` no está instalado en este host (`docker --version` no se reconoce),
  por lo que no se iniciaron PostgreSQL, Redis ni object storage. Las probes de
  este recorrido son locales y no sustituyen los checks de infraestructura.
- La lectura del manifiesto web es de sólo lectura y no realiza fetch, conexión
  durable ni escritura. Un manifiesto ausente hace que `/ready` devuelva
  `503/not_ready` y `/version` un problema sanitizado `503`.
