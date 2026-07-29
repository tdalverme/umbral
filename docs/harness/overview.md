# Harness de desarrollo

El harness es el loop local de feedback para personas y agentes. Su objetivo
es detectar cambios incompatibles con la documentacion y la arquitectura antes
de empezar el desarrollo funcional, sin convertir la V1 en una plataforma de
CI.

## Punto de entrada

Desde la raiz del repo:

```powershell
.\scripts\check.ps1
```

El comando devuelve codigo `0` si no hay fallos bloqueantes y `1` si falla un
check requerido. Cada resultado se marca como `PASS`, `FAIL` o `SKIP`.

## Checks actuales

| Check | Cuando corre | Que protege |
| --- | --- | --- |
| Documentacion | Siempre | Archivos requeridos, limite de `AGENTS.md`, placeholders de la constitucion y tabla de endpoints. |
| Arquitectura | Cuando existe `src/umbral` o `umbral` | Imports prohibidos desde dominio, aplicacion y agent. |
| Spec Kit | Si existe `.venv/Scripts/specify.exe` | Estado de la instalacion e integraciones. |
| API | Cuando existe `umbral.api.main` | Import de la app y presencia de `/health` en OpenAPI. |
| Tests | Cuando hay `.py` bajo `tests/` | Suite automatizada mediante `pytest`. |

Los `SKIP` actuales son esperados porque la aplicacion todavia no esta
scaffolded. Cuando aparezca cada superficie, el mismo comando debe empezar a
verificarla sin cambiar el workflow del equipo.

## Regla de crecimiento

Agregar un check solo cuando exista una regresion concreta que pueda detectar
de forma mecanica. Cada check debe tener una salida accionable y una razon
clara para ser requerido, opcional o salteable. No agregar Docker, CI complejo,
hooks, browser automation ni observabilidad operativa hasta que el producto
tenga una superficie que los necesite.
