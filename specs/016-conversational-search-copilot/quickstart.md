# Quickstart de aceptación: Copiloto conversacional

## Precondiciones

- PostgreSQL con PostGIS y pgvector disponible.
- Backend y frontend configurados según el README del repositorio.
- Dataset de trayectorias v2 cargado con la transcripción canónica y variantes.

## Verificación local prevista

```powershell
.venv\Scripts\Activate.ps1
pytest tests\unit\application\preferences -q
pytest tests\unit\application\conversation -q
pytest tests\unit\application\radar tests\unit\application\scoring -q
pytest tests\contract\test_agent_*_v4.py tests\contract\test_conversation_trajectories_v2.py -q
pytest tests\integration\api\test_chat_copilot_e2e.py -q
npm --prefix apps\web test
npm --prefix apps\web run build
.\scripts\check.ps1
```

## Escenario 1 — Primer turno crea un radar parcial

1. Iniciar sesión sin `search_profile_id`.
2. Enviar `Quiero un depto luminoso y cerca del subte`.
3. Verificar un `state` antes de un segundo.
4. Consultar el radar enlazado.

Resultado esperado:

- radar activo con `zones=[]`, `budget_max=null`, `min_rooms=null`;
- dos expresiones activas;
- cada expresión tiene binding estructurado, semántico o unresolved explícito;
- no se pregunta zona antes de persistir;
- el refresh se informa sin bloquear el input.

## Escenario 2 — Acción pendiente y acto adicional

1. Provocar una propuesta de filtro duro.
2. Enviar `Sí, confirmo, y también quiero balcón`.

Resultado esperado:

- la propuesta pendiente se aplica una sola vez;
- balcón se registra en el mismo turno;
- no se crea feedback de listing;
- no se pierde el texto posterior a “confirmo”.

## Escenario 3 — Preferencia fuera del catálogo

1. Enviar `Quiero una cocina grande y cafés donde pueda trabajar`.
2. Consultar la vista estructurada de preferencias.

Resultado esperado:

- ambas frases permanecen completas;
- ninguna respuesta enumera “preferencias permitidas”;
- cada binding muestra `structured`, `semantic`, `unresolved` o `forbidden`;
- si no hay evidencia, su contribución es cero.

## Escenario 4 — Corrección

1. Con balcón activo, enviar `En realidad el balcón no me importa`.
2. Consultar expresiones y perfil en el turno siguiente.

Resultado esperado:

- la expresión previa queda superseded/withdrawn;
- no hay criterio activo de balcón;
- el cambio suave no pide confirmación;
- el estado anterior sigue auditable.

## Escenario 5 — Cero resultados

1. Aplicar un filtro duro que excluya todos los candidatos.
2. Esperar el run vigente.

Resultado esperado:

- diagnóstico identifica filtros responsables;
- se ofrece al menos una relajación concreta;
- no se modifica el radar;
- preferencias suaves no aparecen como causa de exclusión.

## Escenario 6 — Cambios rápidos

1. Enviar dos refinamientos consecutivos antes de terminar el primer refresh.
2. Esperar ambos jobs.

Resultado esperado:

- la versión nueva queda visible inmediatamente;
- el run anterior termina `superseded` o no se ejecuta;
- solo la última versión puede actualizar `latest_run_id`.

## Gate de producto

La implementación no queda habilitada para beta hasta cumplir simultáneamente:

- 100% de invariantes críticos;
- 95% de trayectorias completas y 90% por familia;
- p95 de respuestas normales menor a cinco segundos;
- al menos ocho participantes, 80% de tareas sin ayuda, facilidad mediana 6/7;
- cero loops irrecuperables y cero mutaciones sobre el objeto equivocado.
