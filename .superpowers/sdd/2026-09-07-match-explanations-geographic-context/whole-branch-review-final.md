# Whole-branch final independent review + post-fix verification

- Spec: PASS
- Quality: PASS

Fecha: 2026-09-08, America/Buenos_Aires.
Worktree: `D:\Tomi\dev\umbral\.worktrees\match-explanations-geographic-context`.
Rama verificada: `feat/match-explanations-geographic-context`.
Independent review HEAD: `24e19ff`.
Post-fix verification HEAD: `a47aba7`.
Base: `72ebf51af46d30b0fd17a8e268472b9597cbcd0c`.

Los dos Major señalados en el pedido y el Minor de redacción quedaron corregidos. No se encontraron issues Blocker, Critical ni Major en esta verificación. No se declara que los checks globales del repositorio estén verdes.

Se leyeron AGENTS.md, PRODUCT.md, el hardening brief y los briefs de tareas aplicables. El paquete `review-72ebf51..6eff75a.diff`, después de su encabezado de commits/stat, coincide exactamente con `git diff -U10 72ebf51...6eff75a`. Se inspeccionó además el código de HEAD y se ejecutaron tests/probes nuevos en esta sesión; los informes anteriores no se usaron como prueba de corrección.

## Strengths

### Correcciones prioritarias, verificadas con calculador urbano v2 real

Se ejecutó el recorrido `UrbanSignalCalculator -> build_observation -> score_candidates -> build_explanation -> build_narrative_context -> deterministic_narrative/ManagedExplanationNarrativeWriter`, usando `contracts/urban/v2/urban-contract-v2.json`. El gateway managed fue el fake controlado `ScriptedGateway`; el calculador, scoring, proyección y validación fueron los reales.

| Probe | Resultado observado | Veredicto |
| --- | --- | --- |
| Bus a 50/60/70 m, tren a 250 m, subte a 2.000 m; acceso_transporte positivo | Señal agregada `0.6`; `context.geography == ()`; tradeoff `con subte a una distancia mayor`; fallback `Encaja con parte de lo que buscás. Con subte a una distancia mayor es un punto para revisar.` | PASS |
| Mismo caso, managed intenta `Encaja por con subte a una distancia mayor.` con ref válida | Rechazado y sustituido por fallback | PASS |
| Mismo caso, managed usa solamente `Con subte a una distancia mayor es un punto para revisar.` con criterio/ref exactos | Aceptado como managed | PASS |
| Avenida y highway a 40 m; ruido_transito positivo | Señal `1.0`; sólo hecho `con una avenida principal relativamente cerca`; sin descriptor `menor exposición` | PASS semántico; Minor gramatical abajo |
| Avenida y highway a 40 m; ruido_transito negativo | Mismo hecho concreto en tradeoff, sin match geográfico | PASS |
| Avenida y highway a 500 m; ruido_transito positivo | Señal `0.0`; `alejada de los principales corredores` en tradeoff | PASS |
| Avenida y highway a 500 m; ruido_transito negativo | Mismo hecho en geografía favorable | PASS |

La dirección del contributor concreto se fija en `src/umbral/application/scoring/narrative.py:437`, con umbrales en `:547` y `:549`; la polaridad se aplica una vez en `:449`. La supresión de la razón geográfica genérica está en `:336`, particularmente el conjunto de `:340`. Los tests ejecutados están en `tests/unit/application/scoring/test_narrative_end_to_end.py:205` y `:289`; la aceptación/rechazo managed específica del subte está en `:322` y `:332`.

### Regresiones y trazabilidad

| Área pedida | Evidencia de HEAD y ejecución | Resultado |
| --- | --- | --- |
| Writer canonical, negaciones y claims añadidos | `src/umbral/infrastructure/scoring/narrative.py:192` exige igualdad del texto completo con la secuencia canónica; tests `tests/unit/infrastructure/scoring/test_narrative_writer.py:246`, `:381`, `:393`, `:427` | PASS |
| Placement match/tradeoff | Render según placement en `src/umbral/infrastructure/scoring/narrative.py:330`; tests writer `:345` y caso real subte `test_narrative_end_to_end.py:332` | PASS |
| Precio inventado/invertido/incompleto | Tests writer `:271`, `:443`; `tests/unit/application/scoring/test_narrative.py:418`, `:432`, `:448`; proyección de cambios en `src/umbral/application/scoring/narrative.py:775` | PASS |
| Refs vacías, ajenas, no renderizadas; canonical exacto | Tests writer `:169`, `:304`, `:460`; igualdad de conjuntos de criterios/refs en `src/umbral/infrastructure/scoring/narrative.py:323` y `:325` | PASS |
| Provenance exacta del fallback | `src/umbral/application/scoring/narrative.py:165` deriva criterios/refs de elementos seleccionados; `tests/unit/application/scoring/test_narrative.py:658` comprueba que geografía no renderizada no se declare | PASS |
| Cero y unsupported | Tests reales v2 de daily/nightlife en `test_narrative_end_to_end.py:143` y `:174`; pruebas de conteos cero y señales no soportadas en `test_narrative.py:154` y `:516`; descarte de razones urbanas sin hecho en `narrative.py:323` | PASS |
| Categorías v2, tren/subte y terms ajenos | `test_narrative.py:222`, `:496`; validación de prefijos por señal en `src/umbral/application/scoring/narrative.py:501` | PASS |
| Road near/far, positivo/negativo | Cuatro combinaciones ejecutadas con calculador v2, tabla anterior y test `test_narrative_end_to_end.py:205` | PASS |
| Enums luminosidad y estado_general | Tests reales `test_narrative_end_to_end.py:343`, `:380`; mapeo de `baja/media/alta` y `malo/regular/bueno/muy_bueno` en `src/umbral/application/scoring/narrative.py:689` y `:703` | PASS |
| Snapshot congelado y listing identity | `src/umbral/application/scoring/service.py:325`, `:599`, `:614`; tests `test_narrative_service.py:111`, `:137`, `:178`, `:201` cubren datos actuales alterados e identidad ajena/ausente | PASS |
| Run omitido resuelto una vez | `src/umbral/api/routers/explanations.py:249` y reutilización en `:255`, `:264`; `tests/contract/test_explanation_endpoints.py:268` | PASS |
| Labels humanos | `narrative_label` en `src/umbral/application/scoring/narrative.py:761`; test de cobertura contractual `test_narrative.py:635`; fallback genérico para key desconocida | PASS |
| Unknown copy del sheet | `apps/web/src/lib/radar/criterion-labels.ts:45`; sheet `opportunity-detail-sheet.tsx:149`, `:152`; test DOM `opportunity-detail-sheet.test.tsx:93` | PASS |
| Unknown copy del full detail | `apps/web/src/app/(protected)/listings/[id]/page.tsx:34`, `:39` usa los mismos helpers; test compartido `apps/web/src/lib/radar/criterion-labels.test.ts:6` | PASS por helper ejecutado + inspección de ambas llamadas; sin navegador |
| Same identity UI | `apps/web/src/lib/radar/narrative-selection.ts:1`; tests `narrative-selection.test.ts:6`, `:16`; shell preserva resultado en `radar-shell.tsx:62`, cancela respuesta vieja y valida listing/run en `:80` | PASS por helper ejecutado + inspección del efecto |
| Narrativa sólo al seleccionar | `include_narrative` default false en router `explanations.py:240`; list no llama writer (`test_narrative_service.py:126`); BFF query y payload cubiertos por `apps/web/src/app/api/radar/profiles/[id]/explanations/[listingId]/route.test.ts` | PASS |

Además de la suite, se ejecutaron probes en stdin que imprimieron las seis combinaciones de geografía/polaridad descritas. La revisión Spec paralela ejecutó las seis funciones end-to-end y cinco probes adversariales del writer: canonical aceptado; negación, amenity añadida, placement invertido y precio inventado rechazados. No se escribieron archivos de probes.

### Alcance e invariantes

**Standards: PASS**, sin violaciones arquitectónicas accionables ni refactors sugeridos por heurísticas. La revisión Spec encuentra únicamente el Minor listado abajo.

- Contra **72ebf51**, la rama **sí cambia activación y normalización de scoring**, de forma expresamente autorizada por `task-1-brief.md` (pasos 4/5): `src/umbral/application/scoring/active_criteria.py:1`, `engine.py:151`, `engine.py:309`. No sería correcto afirmar que toda la rama mantiene scoring/activation idénticos a esa base. Los tests de criterios activos, pesos, publicación, hard/soft y unknown están incluidos en los 171 tests ejecutados.
- Contra **e1f21b1**, la base explícita del hardening (`hardening-task-1-brief.md:5`), `engine.py` sólo añade `listing_id` al snapshot (`engine.py:275`) y formato; `active_criteria.py` y el calculador urbano no cambian. El cambio inicial de `urban/calculator.py:94` retiene valores/unidades del contributor, sin modificar el cálculo de la señal.
- No hay cambios a modelos persistentes ni migraciones; tampoco a módulos de matching/hard filters/notificaciones en el diff de la rama. El hardening no altera fórmulas de score, ordenamiento, activación ni puertas de notificación. Matching y notificaciones sumaron otros 52 tests PASS.
- El LLM queda detrás del puerto de aplicación `src/umbral/application/scoring/ports.py:125` y del adapter `src/umbral/infrastructure/scoring/narrative.py:52`; recibe un contexto acotado, valida contra hechos autorizados y retorna copy. No tiene acceso de escritura al ranking, filtros ni notificaciones.

## Issues Blocker/Critical/Major/Minor

### Blocker

Ninguno encontrado.

### Critical

Ninguno encontrado.

### Major

Ninguno encontrado. Ambos Major del pedido quedaron cerrados con evidencia ejecutada en esta sesión.

### Minor — Conector duplicado en la narrativa geográfica favorable

**Severidad: Minor. Reproducible en fallback y managed.**

Para `ruido_transito` con polaridad positiva y avenida a 40 m, el resultado literal es:

> Encaja por con una avenida principal relativamente cerca.

`src/umbral/application/scoring/narrative.py:116` antepone `Encaja por` al descriptor iniciado con `con` de `:596`. El renderer managed repite la composición en `src/umbral/infrastructure/scoring/narrative.py:335`. El test en `tests/unit/application/scoring/test_narrative_end_to_end.py:282` actualmente fija esa frase y `:285` confirma que también se acepta como managed.

El hecho concreto, su polaridad y sus referencias son correctos, por eso no se reabre el Major de exposición. El defecto es de sintaxis visible para la persona y contradice la voz natural/conversacional exigida por `PRODUCT.md:79`, `:81`, `:118` y `hardening-task-1-brief.md:23`.

Reproducción mínima, desde el worktree y con el entorno Python indicado abajo:

```powershell
& $py -m pytest -p no:cacheprovider tests/unit/application/scoring/test_narrative_end_to_end.py::test_v2_road_noise_applies_user_polarity_once -q
```

Ese test pasa porque espera la frase defectuosa. Para observarla directamente, se ejecutó este probe de la ruta real en stdin:

```python
from uuid import uuid4
from tests.unit.application.scoring.test_narrative_end_to_end import (
    CONTRACT_PATH, _urban_observation, _narrative_for_observation,
)
from umbral.application.urban.calculator import UrbanSignalCalculator
from umbral.application.urban.contract import load_urban_contract
calc = UrbanSignalCalculator(load_urban_contract(CONTRACT_PATH))
result = calc.calculate(linear_distances={
    "major_road": {"nearest_m": [40.0]},
    "highway": {"nearest_m": [40.0]},
})
context, fallback, managed = _narrative_for_observation(
    concept_key="ruido_transito", polarity="positive",
    observation=_urban_observation(
        listing_id=uuid4(), concept_key="ruido_transito",
        signal_ref="road_noise", result=result,
    ),
)
print(fallback.text)
print(managed.source, managed.text)
```

Corrección recomendada: componer la oración de forma gramatical en ambos renderers, conservando el mismo hecho, placement y provenance; actualizar la expectativa del test. No se aplicó ninguna corrección durante esta revisión.

## Tests/comandos y resultados

Entorno usado para todos los comandos Python:

```powershell
Set-Location D:\Tomi\dev\umbral\.worktrees\match-explanations-geographic-context
$py = 'D:\Tomi\dev\umbral\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
$env:PYTHONDONTWRITEBYTECODE = '1'
```

| Comando | Resultado de esta sesión |
| --- | --- |
| `git rev-parse HEAD`; `git rev-parse 72ebf51`; `git branch --show-current`; `git log 72ebf51..HEAD --oneline` | Identidad y 24 commits verificados |
| Comparación en memoria del paquete con `git diff -U10 72ebf51...6eff75a` | Igualdad exacta de la sección diff |
| `& $py -m pytest -p no:cacheprovider tests/unit/application/scoring tests/unit/application/urban tests/unit/infrastructure/scoring tests/contract/test_explanations.py tests/contract/test_explanation_endpoints.py tests/contract/test_explanation_narrative.py -q` | **171 passed**, 11 warnings, exit 0 |
| `& $py -m pytest -p no:cacheprovider tests/unit/application/matching tests/unit/application/notifications tests/contract/test_matching_golden.py tests/contract/test_notifications_policy.py -q` | **52 passed**, exit 0 |
| Probes reales de geografía ejecutados vía Python/stdin | Seis combinaciones de contributor/polaridad, resultados impresos y consignados arriba, exit 0 |
| Revisión Standards: tests narrative_service + explanation_endpoints | **14 passed**, 11 warnings, exit 0; subconjunto de la suite principal, no sumar como cobertura distinta |
| `& $py -m pytest -p no:cacheprovider tests/integration/scoring tests/integration/urban --collect-only -q` | **23 tests collected**, exit 0 |
| `& $py -m pytest -p no:cacheprovider tests/integration/scoring tests/integration/urban -q -x` | Exit 1 en setup del primer test: DockerException, no existe `//./pipe/docker_engine`; ninguna aserción de integración validada |
| `npm test --workspace @umbral/web` | Primera ejecución: 60 tests/26 archivos pasaron, pero 7 workers no arrancaron por timeout; exit 1, no se cuenta como suite verde |
| Desde `apps/web`: `node D:\Tomi\dev\umbral\node_modules\vitest\vitest.mjs run --maxWorkers=1` | **84 tests, 33 archivos PASS**, exit 0, 45.75 s |
| `npm run typecheck --workspace @umbral/web` | `tsc --noEmit` PASS, exit 0 |
| `& $py -m ruff check --no-cache src tests` | Exit 1; **22 diagnósticos**, detallados como baseline abajo |
| Ruff sobre los 28 archivos Python modificados | Exit 1; sólo 7 E501 previos en radar/service.py; cero diagnósticos en la implementación narrativa y sus fixtures nuevos |
| `& $py -m mypy --cache-dir=nul src tests` | Exit 1; **178 errores en 34 archivos, 775 archivos comprobados**; sin errores en módulos narrativos ni nuevos fixtures |
| `npm run lint --workspace @umbral/web` | Exit 1; **7 errores y 14 warnings**, diferenciados contra base abajo |
| `git diff --check 72ebf51...HEAD` | PASS, exit 0 |

El intento inicial de pasar `--reporter=dot` a través de npm fue rechazado por esta versión de npm (`EUNKNOWNCONFIG`), antes de ejecutar tests. Se corrigió la invocación. Un primer intento del reviewer Standards sin PYTHONPATH falló colección por `ModuleNotFoundError: umbral`; el reintento con PYTHONPATH al worktree pasó. Ninguno se atribuye al producto.

### Typing/lint: distinción del baseline

- **Ruff:** los 22 diagnósticos aparecen sobre líneas presentes en `72ebf51`. Diez están en `src/umbral/api/routers/listings.py`; siete E501 en `src/umbral/application/radar/service.py:466`, `:467`, `:623`, `:630`, `:693`, `:696`, `:724`; los restantes en tests de playground/delivery y el F401 de `tests/unit/application/scoring/test_hard_soft.py:5`. Se compararon las líneas con `git show 72ebf51:<archivo>`. No se usó `--fix`.
- **mypy:** 33 de los 34 archivos diagnosticados son idénticos entre base y HEAD. El único archivo diagnosticado que también aparece en el diff es `tests/unit/application/scoring/test_run_publish.py:291`: asignación de `conflicting_publish`, cuyo retorno `None` no satisface el callable que devuelve RecommendationRun. El bloque, el ignore `[method-assign]` y la firma problemática ya existen en base (línea 293); el cambio de rama sólo quita dos expectativas de criterios inactivos. Ejemplos de baseline intacto: `tests/integration/agent_ops/conftest.py:6`, `src/umbral/infrastructure/playground/trace.py:18`, `src/umbral/application/preferences/service.py:238`. No se afirma haber ejecutado un checkout completo de base: la atribución usa identidad del archivo/bloque y diff de dependencias relevantes.
- **ESLint:** se ejecutó otra vez con salida JSON y se contrastaron las líneas con base. Además se lintaron **en memoria** las versiones base de los archivos web modificados usando `ESLint.lintText` con el mismo filePath/config: opportunity-detail-sheet conserva 1 error; radar-shell conserva 2; floating-list conserva 1 warning. La página radar baja de 8 warnings en base a 7 en HEAD. Los otros archivos diagnosticados están sin modificar. Los errores de efectos en `opportunity-detail-sheet.tsx:51`, `radar-shell.tsx:100` y `:123` son preexistentes. No hay nuevos errores de lint atribuidos a esta rama.

## Limitaciones

- Docker no está disponible; no se verificaron persistencia real, Postgres/PostGIS ni transacciones de las 23 integraciones. Colección correcta no equivale a ejecución correcta.
- Se usó un gateway managed controlado; no se llamó un proveedor LLM externo. La validación de salida se ejercitó con el adapter real y respuestas adversariales.
- No hubo recorrido manual en Preview/navegador, E2E ni build de producción. Full detail y same-identity tienen la cobertura concreta indicada en la matriz (helper/tests DOM e inspección de wiring); no se presentan como prueba visual o de navegación completa.
- No se ejecutó el harness global `scripts/check.ps1`: incluye checks que exportan contratos/generados y pruebas con servicios. Se respetó el pedido de revisión de sólo lectura con la única edición del informe. Los comandos independientes relevantes, incluidos typing/lint globales, sí se ejecutaron.
- Las warnings Python son deprecaciones Starlette/httpx y cookies. Los fallos globales de typing/lint y la ausencia de Docker quedan documentados, no corregidos.
- Esa revisión no modificó código, tests, briefs, modelos, migraciones ni commits; la corrección posterior queda documentada en la sección final. No se publicó ni se hizo merge.

## Final copy correction

El Minor fue corregido en `24e19ff` sin modificar placement, grounding, contributors, scoring ni provenance:

- La composición de match normaliza sólo el prefijo geográfico `con ` antes de anteponer `Encaja por`, produciendo `Encaja por una avenida principal relativamente cerca.`.
- Los tradeoffs mantienen el descriptor original (`Con una avenida principal relativamente cerca es un punto para revisar.`) y el managed writer aplica la misma composición canónica.
- La regresión end-to-end de fallback y managed fue actualizada; la forma gramatical nueva es aceptada y la cobertura previa de claims falsos/provenance permanece vigente.

### Final verification

- TDD RED: la regresión de ruido vial positivo falló con la frase `Encaja por con ...` antes del ajuste.
- TDD GREEN: focused narrative/writer/end-to-end `49 passed`.
- Relevant backend suite: `185 passed, 11 warnings`; adjacent backend suite: `185 passed`.
- Web: `33 archivos / 84 tests passed`; typecheck passed.
- Ruff y mypy focalizados: passed. `git diff --check`: passed.
- No hay cambios en scoring/ranking, modelos, migraciones, filtros, activación, notificaciones ni decisiones LLM.

**Conclusión final:** el único Minor de redacción queda resuelto; la rama está lista para handoff, con las limitaciones y diagnósticos baseline ya documentados.

## Post-fix verification at `a47aba7`

The independent reviewer could not complete a second review after the final copy
commit because the Codex review host reached its usage limit. The final code
change was verified locally from the current worktree instead:

- Direct narrative/writer/end-to-end/endpoint slice: `67 passed, 11 warnings`.
- Backend scoring/urban/contracts slice: `171 passed`; adjacent radar,
  matching, notification, criteria and voice slice: `204 passed`.
- Web suite: `33 files / 84 tests passed`; TypeScript typecheck passed.
- Targeted mypy has no errors in the changed narrative source/tests; the
  remaining diagnostics are the documented baseline errors in unrelated
  modules. Ruff has only the seven documented pre-existing `E501` diagnostics
  in `radar/service.py`.
- `git diff --check` passed and the worktree is clean.

The final copy regression specifically asserts `Encaja por una avenida
principal relativamente cerca.` and preserves the managed canonical boundary.
