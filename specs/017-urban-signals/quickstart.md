# Quickstart de aceptación: Señales urbanas declarativas

## Precondiciones

- PostgreSQL con PostGIS disponible.
- Contrato `urban-contract-v1` registrado como versión de extracción.
- Snapshot de OpenStreetMap importado (Geofabrik Argentina o fixture de prueba).

## Verificación local prevista

```powershell
pytest tests\contract\test_urban_contract.py -q
pytest tests\unit\application\urban -q
pytest tests\integration\urban -q
pytest tests\integration\agent_evals\test_trajectories_v2.py -q
```

## Escenario 1 — El contrato es válido y computable

1. Correr el conformance del contrato.
2. Correr el golden del calculator con primitivas de ejemplo.

Resultado esperado:

- el contrato valida (referencias a primitivas existentes, pesos normalizados, tags válidos);
- las señales de ejemplo computan valores exactos esperados;
- una señal nueva declarada en el contrato computa sin cambios de código.

## Escenario 2 — Pipeline completo sobre un snapshot fixture

1. Importar un snapshot OSM chico (fixture, no el pbf real).
2. Correr el batch: distancias → señales crudas → estadísticas por barrio → normalización.
3. Verificar observaciones urbanas en la base.

Resultado esperado:

- listings con coordenadas precisas tienen señales con `value` y `normalized_value`;
- listings sin coordenadas precisas no tienen señales;
- un barrio con muestra insuficiente usa fallback global con confidence rebajada y `normalization_scope: "caba"`;
- una señal de densidad está normalizada por barrio; una de distancia está absoluta;
- cada observación traza a su contrato y snapshot.

## Escenario 3 — Puente conversacional

1. Correr la trayectoria de puente que seedea una observación urbana.
2. Enviar "quiero estar cerca de cafes".

Resultado esperado:

- el deseo se conserva completo;
- se vincula a la señal `cafe_lifestyle` existente (no `unresolved`);
- la contribución no es cero cuando hay evidencia;
- la explicación cita los datos crudos sin mencionar OpenStreetMap.

## Escenario 4 — Reimport y recálculo

1. Reimportar un snapshot con cambios.
2. Correr el batch.

Resultado esperado:

- el 100% de los listings con coordenadas precisas se recalculan;
- ningún listing conserva señales del snapshot anterior;
- la tabla de estadísticas por barrio se recalcula en el mismo job.

## Gate de producto

La feature queda habilitada cuando simultáneamente:

- el 100% de las señales declaradas en el contrato se computan y persisten;
- el 100% de las señales de densidad se normalizan por barrio y las de distancia permanecen absolutas;
- una señal nueva se agrega sin cambios en el scoring;
- la atribución de OpenStreetMap es visible en una superficie global;
- las trayectorias conversacionales existentes siguen pasando.
