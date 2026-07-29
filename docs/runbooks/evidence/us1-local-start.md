# Evidencia US1 — arranque local de foundation-runtime

**Fecha:** 2026-07-29 (America/Argentina/Buenos_Aires; evidencia reconciliada al cierre)
**Superficie:** API FastAPI + web Next.js 16.2.12  
**Release observado:** `foundation-local` (manifiesto sentinel local); fixture
de contrato `foundation-20260101` validada por separado.  
**Resultado:** PASS para los gates ejecutados; sin efectos persistentes.

## Registro cronometrado

| Paso | Comando | Resultado observado | Tiempo aproximado |
| --- | --- | --- | ---: |
| Toolchain | `node --version`, `npm.cmd --version`, `python --version` | Node `v24.15.0`, npm `12.0.1`, Python `3.13.14` | <1 s |
| API probes | `PYTHONPATH=src python -c ... TestClient ...` | `/health=200`, `/ready=200`, `/version=200`; `no-store`; `foundation-local` | 2.2 s |
| OpenAPI export | `scripts/export-openapi.ps1` | JSON 3.1 ordenado generado | 1.6 s |
| Compatibilidad | `scripts/check-contracts.ps1` | PASS, cambios breaking rechazables | 0.9 s |
| Cliente | `npm.cmd run api:check --workspace @umbral/web` | Hey API `0.99.0`, cinco archivos, diff limpio | 2.8 s |
| Python | `scripts/check-python.ps1` con `NPM_EXECUTABLE` npm 12 | Ruff/mypy PASS, `146 passed` | actualizado al cierre |
| Web gates | `scripts/check-web.ps1` | ESLint/TS/Vitest PASS (`13`), Playwright lista (`6`) | actualizado al cierre |
| Build | `npm.cmd run build --workspace @umbral/web` | Next build PASS; `.next/standalone`; warning NFT dinámico documentado | ~67 s |

## Comandos reproducibles

```powershell
$env:PATH = (Join-Path (Get-Location) '._tmp_npm12') + ';' + $env:PATH
$env:NPM_EXECUTABLE = (Join-Path (Get-Location) '._tmp_npm12\npm.cmd')

$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m pytest `
  tests\contract\test_runtime_api_contract.py `
  tests\contract\test_http_correlation_and_errors.py `
  tests\contract\test_openapi_versioning.py `
  tests\contract\test_generated_client.py `
  tests\unit\config\test_settings.py `
  tests\unit\runtime\test_version.py `
  tests\unit\runtime\test_readiness.py -q

.\scripts\export-openapi.ps1 -OutputPath contracts\openapi\v1\openapi.json
.\scripts\check-contracts.ps1
npm.cmd run api:check --workspace @umbral/web
.\scripts\check-python.ps1
.\scripts\check-web.ps1
npm.cmd run build --workspace @umbral/web
```

La suite completa usada por `check-python.ps1` terminó `146 passed` cuando el
ejecutable npm se fijó a npm 12. La web expuso la ruta estática `/` y las rutas dinámicas `/health`,
`/ready` y `/version` en el build.

## Brechas explícitas

1. La colección Playwright se enumeró (`6 tests`) pero no se ejecutó: falta un
   servidor web iniciado con un manifiesto montado y un navegador en esta
   sesión.
2. No se usó Docker porque el binario no está instalado; por eso no hay
   evidencia de PostgreSQL/Redis/object storage reales en este arranque.
3. El entorno Windows requiere seleccionar Node 24/npm 12 antes de ejecutar el
   harness. El `npm.cmd` global de Node 22 produce un error `EPERM` al resolver
   `C:\Users\Usuario`; con el wrapper npm 12 todos los gates anteriores pasan.
4. El warning de Turbopack sobre NFT amplio proviene de la ruta configurable del
   manifiesto y no cambia el resultado de build; debe revisarse al empaquetar
   una imagen de release.
