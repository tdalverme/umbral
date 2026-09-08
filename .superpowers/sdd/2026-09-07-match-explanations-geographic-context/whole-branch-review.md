# Whole-branch review independiente

- **Spec: PASS** (after the correction round documented below)
- **Quality: PASS** (after the correction round documented below)

Revisión del 2026-09-08 sobre `feat/match-explanations-geographic-context`, HEAD `f5adc16a7ec51f309414370b3bd46c35b9f5e44b`, base `72ebf51`. Worktree exacto: `D:\Tomi\dev\umbral\.worktrees\match-explanations-geographic-context`. Las referencias `archivo:línea` de este informe son relativas a ese worktree y corresponden al HEAD revisado.

Leí `AGENTS.md` y `PRODUCT.md` de la raíz, el brief de hardening y los briefs originales de tareas 1–7. El brief y el paquete de diff no existen en las rutas suministradas bajo la raíz principal: utilicé las copias del worktree. Verifiqué que la sección `## Diff` del paquete `review-72ebf51..f5adc16.diff` coincide exactamente con `git diff --unified=10 72ebf51 f5adc16` (45 archivos). SHA-256 del paquete: `ad1309a3acc883ca6059634e898f5c121304441f5ffe39019b9d124d8fb8d816`.

No modifiqué código, tests ni briefs; no creé subagentes. Este informe es el único archivo escrito deliberadamente. El cambio local previo en `hardening-task-1-review.md` quedó intacto.

## Strengths

- La activación tiene una regla compartida para scoring y explicación (`src/umbral/application/scoring/active_criteria.py:16`, `engine.py:93`, `service.py:500`). Excluir criterios no declarados y renormalizar pesos estaba expresamente pedido por la tarea 1; no lo considero un cambio de alcance ni exijo igualdad de scores con la base anterior.
- El LLM se invoca al consultar el detalle optativo, después de obtener el resultado determinístico; no participa en ranking, hard filters, publicación ni notificaciones (`service.py:294`, `src/umbral/api/routers/explanations.py:258`). El listado no invoca el writer. El gateway usa cero retries y el timeout existente (`src/umbral/infrastructure/runtime/composition.py:325`).
- El endpoint resuelve una sola vez el run omitido y lo reutiliza para breakdown y narrativa (`src/umbral/api/routers/explanations.py:249`). Los snapshots de listing/observaciones se guardan con el item y la rehidratación descarta identidades de otro listing o ausentes (`src/umbral/application/radar/service.py:749`, `src/umbral/application/scoring/service.py:322`, `service.py:605`).
- El writer valida schema, criterios y referencias autorizadas, términos técnicos y voz; falla a una implementación determinística ante errores del proveedor. La separación aplicación/puerto/adapter es apropiada.
- La distinción tren/subte y el rechazo de contributors ajenos están implementados. El fallback limita hechos y computa provenance a partir de las selecciones renderizadas; hay pruebas sobre geografía no renderizada y snapshots cruzados.
- No hay cambios de modelos DB, migraciones, dominio ni implementación de notificaciones en este diff. Las pruebas focalizadas y adyacentes ejecutadas dan 340 tests backend aprobados; los 80 tests web y el typecheck web también pasan.

Estas fortalezas no cierran las fallas semánticas reproducidas a continuación. Un vocabulario autorizado y referencias válidas todavía permiten afirmar algo que el hecho no sostiene.

## Issues Blocker/Critical/Major/Minor

**Blocker: ninguno identificado. Critical: ninguno identificado. Hay 5 issues Major y 4 Minor.**

### Major 1 — El grounding managed valida palabras y presencia de descriptores, pero acepta contradicciones y cambios de precio invertidos

**Evidencia:** `src/umbral/infrastructure/scoring/narrative.py:324` busca un descriptor y un marcador en alguna frase; `:343` valida tokens como una bolsa de palabras; `:280` y `:399` solo verifican que aparezcan ambos importes y la moneda. No se verifica la negación, que todas las frases tengan soporte, ni la dirección/orden de una transición de precio. La validación tampoco exige que cada referencia declarada se renderice.

Con la fixture real `context` de `tests/unit/infrastructure/scoring/test_narrative_writer.py:69` y el writer real, estos outputs se aceptaron con `source='managed'`:

| Packet / metadata | Texto aceptado que viola el packet |
| --- | --- |
| Match de conectividad y su ref autorizada | `No encaja por la buena conectividad.` |
| Mismo match/ref | `Encaja por la buena conectividad. No tiene buena conectividad.` |
| Conectividad match + superficie mismatch, ambas refs | `Encaja por la buena conectividad y la superficie. La superficie es un punto para revisar.` |
| Cambio `before=900, after=800, currency=USD` y ref de precio | `Encaja por la buena conectividad. Subió de USD 800 a USD 900.` |
| Packet con precio, ref de transporte y ref de precio declaradas | `Encaja por la buena conectividad.` — conserva `listing_field:price` aunque no utiliza ese hecho |

Impacto: se devuelve como confiable texto que niega el match, convierte una concesión en coincidencia o invierte una baja real; provenance puede declarar hechos no utilizados. Viola el cierre claim→hecho→criterio→ref del brief. Corregir la autorización semántica de cada claim, incluyendo polaridad, placement y transición ordenada; una opción acotada es que el modelo seleccione descriptores/claims tipados y código renderice su contenido autorizado. No basta con ampliar regexes o vocabulario.

### Major 2 — Cantidad cero y distancia desfavorable se transforman en hechos geográficos favorables

**Evidencia:** `src/umbral/application/scoring/narrative.py:427` devuelve `True` para transporte, parques, servicios, cafés, comercio y vida nocturna independientemente de la medición; `:520`–`:541` no distingue cero de una cantidad positiva. `build_narrative_context` conserva esos hechos favorables incluso cuando la evaluación es mismatch (`:314`).

Probe con el calculador y contrato publicado: `cafe.count_300m=[900.0]` y `cafe.nearest_m=[900.0]` producen un contributor válido con `observed_value=0`, score `0.0`, confidence `1.0`. `geographic_facts` lo traduce a **“algunos cafés cerca”**. En un packet de mismatch con ese contributor el fallback devolvió **“Encaja por algunos cafés cerca. Cafés cercanos es un punto para revisar.”** Otro probe con subte a 2.000 m devolvió **“Encaja por con subte a una distancia mayor. Buena conectividad es un punto para revisar.”**

Impacto: aun sin proveedor, la explicación inventa presencia o vende una distancia desfavorable como razón de selección. Para una preferencia negativa, la misma constante favorable puede convertir la ausencia deseada en concesión. La clasificación debe considerar medición, dirección y criterio evaluado; cero no autoriza “algunos”.

### Major 3 — El fallback pierde la dirección de las preferencias no geográficas

**Evidencia:** `src/umbral/application/scoring/narrative.py:549` proyecta cada evaluación como label/state/ref, omitiendo el valor y dirección que hicieron que coincidiera; `:101`–`:115` renderiza el label como una cualidad positiva. `_narrative_criteria` conserva `polarity` en las prioridades (`src/umbral/application/scoring/service.py:566`), pero no la aplica a esos descriptores.

Probe completo usando `ScoringTestContext`, scoring real y `build_explanation`: criterio `luminosidad`, `semantic_feature`, `polarity='negative'`, observación `score=0.1`. Scoring devuelve correctamente `match`, score `0.9`; el fallback devuelve **“Encaja por buena luz natural.”** La propiedad tiene poca luz según el mismo input. No es una cuestión de estilo: afirma lo contrario del hecho que originó el match. La validación managed también recibe ese descriptor incorrecto como autorizado.

Corregir la proyección de hechos para que incluya el valor/dirección efectivamente satisfecho, en vez de convertir un nombre de prioridad en una afirmación de presencia/calidad. Mantener el scoring determinístico existente.

### Major 4 — Tres señales soportadas nunca obtienen hechos con el contrato publicado

**Evidencia:** `src/umbral/application/scoring/narrative.py:469` admite `park.*` para `green_access`, `service.*` para `daily_convenience` y `commercial.*` para `commercial_intensity`. El contrato cargado en producción es v2 (`src/umbral/infrastructure/urban/contract_loader.py:13`), que utiliza:

- `green_space.*` para parques (`contracts/urban/v2/urban-contract-v2.json:129`).
- `supermarket.*`, `pharmacy.*`, `convenience.*`, `health.*` para servicios (`:70`).
- `restaurant.*`, `cafe.*`, `supermarket.*`, `shopping_mall.*` para comercio (`:105`).

El probe construyó contributors desde las fórmulas reales del JSON, con cinco lugares o distancia de 150 m, y `geographic_facts` devolvió `()` para las tres señales. No son señales deliberadamente fuera del alcance: figuran en el adaptador y en el brief de tarea 3. Alinear las categorías autorizadas con el contrato real y probar ese recorrido, preservando la semántica específica de cada contributor.

### Major 5 — No se cumple el gate de typing de los tests nuevos

**Evidencia y resultado:** mypy estricto sobre las fuentes narrativas y tests de scoring devuelve 18 errores. **17 son nuevos en la rama**:

- `tests/unit/application/scoring/test_active_criteria.py:16`: helper `_policy` sin retorno tipado y llamadas no tipadas en `:28` y `:42` (3 errores).
- `tests/unit/application/scoring/test_run_scoring.py:122`, `:131` y `:145`: `common` se infiere como `dict[str, object]`; expandirlo en `score_candidates` genera 14 errores de argumentos.

El restante, `tests/unit/application/scoring/test_run_publish.py:291`, ya existe en `72ebf51` y no se atribuye a esta rama. Los tres módulos narrativos de producción sí pasan mypy aislados. El brief exige corregir errores introducidos en archivos cambiados, sin ampliar ignores: el resultado whole-branch todavía no cumple ese requisito.

### Minor 1 — La UI inventa la causa o dirección del reparo

**Evidencia:** `apps/web/src/lib/radar/criterion-labels.ts:46` recibe solo key/state, pero para cualquier mismatch de `vida_nocturna` afirma que la zona es **más** activa de noche. Para una preferencia positiva insatisfecha no se puede deducir eso del estado. En `:51` todo unknown pasa a **“el aviso no lo informa”**, incluso si procede de cobertura urbana insuficiente, baja precisión o ausencia de observación, y no de una omisión del aviso. La misma causa se fuerza en `opportunity-detail-sheet.tsx:153`.

Es una afirmación nueva que el payload utilizado no sostiene. Usar una concesión neutral o copy fundada en dirección/causa explícitas del backend. No reemplazar la incertidumbre genérica por una causa no demostrada.

### Minor 2 — La explicación determinística de las cards sigue perdiendo labels de conceptos soportados

**Evidencia:** `src/umbral/application/scoring/explanations.py:22` contiene solo 11 labels; `:168` convierte el resto en “este criterio”. El mapa completo de `narrative.py` no se utiliza en este builder. Para claves soportadas como `vida_nocturna`, `proximidad_parque`, `mascotas` o `tipo_cocina`, las cards pueden decir “La zona muestra buenas señales de este criterio” o “Aparece alineado con este criterio”.

El listado no pide narrativa, así que no recibe el label humano completo de la vista seleccionada. Evita claves crudas, pero no explica qué importa para ese radar y expone “criterio” en copy. Compartir o completar la resolución de labels en el builder usado por las cards.

### Minor 3 — Volver a seleccionar el mismo listing borra la narrativa sin iniciar otra petición

**Evidencia:** `apps/web/src/components/radar/radar-shell.tsx:61` siempre pone `narrativeResult=null` y `narrativeLoading=true`. El effect de `:67` depende solamente de listing, radar y run (`:88`). Si el usuario vuelve a hacer click en la misma card/pin después de terminar la petición, ninguno de esos valores cambia: desaparece la narrativa y queda “Preparando una síntesis…” hasta cambiar de selección. El setter de URL tampoco cambia el ID (`apps/web/src/lib/radar/use-radar-selection.ts:12`).

Conservar el resultado al seleccionar la misma identidad, o hacer coherentes el reset y el disparador de carga. Hallazgo por inspección del ciclo de estado, sin prueba de navegador ejecutada.

### Minor 4 — Se introduce un fallo del lint configurado

**Evidencia:** `src/umbral/application/radar/service.py:754` tiene 90 caracteres frente al límite E501 de 88. `ruff check --no-cache` sobre todos los Python tocados devuelve 8 errores; este es nuevo y los otros 7 corresponden a líneas previas de ese archivo, fuera del diff. La corrección requerida es local, sin reformatear el resto del servicio.

## Tests/commands y resultados

Todos los comandos se ejecutaron desde el worktree indicado salvo el typecheck, ejecutado desde `apps/web`. Para Python se utilizó `D:\Tomi\dev\umbral\.venv\Scripts\python.exe`, `PYTHONPATH=src` y, para pytest/probes, `PYTHONDONTWRITEBYTECODE=1`. No se agregó ningún test al repositorio.

| Comando | Resultado fresco |
| --- | --- |
| `git branch --show-current`; `git rev-parse HEAD`; `git diff --stat 72ebf51 f5adc16` | Rama y HEAD esperados; 45 archivos, +3783/-166. |
| `python -m pytest -p no:cacheprovider tests/unit/application/scoring tests/unit/infrastructure/scoring tests/unit/application/urban tests/contract/test_explanation_endpoints.py tests/contract/test_explanation_narrative.py tests/contract/test_explanations.py -q` | **155 passed**, 11 warnings de deprecación FastAPI/Starlette/httpx; 2,37 s reportados por pytest. |
| `python -m pytest -p no:cacheprovider tests/unit/application/radar tests/unit/application/matching tests/unit/application/notifications tests/unit/application/criteria tests/unit/application/conversation/test_voice_check.py -q` | **185 passed**, 9,52 s. |
| `npm test --workspace @umbral/web -- opportunity-detail-sheet floating-list explanations` | **3 archivos, 4 tests passed**. |
| `npm test --workspace @umbral/web` | **31 archivos, 80 tests passed**, 41,64 s. Incluye los cuatro anteriores. |
| `node D:/Tomi/dev/umbral/node_modules/typescript/bin/tsc --noEmit --incremental false` | **PASS**, exit 0. Se utiliza el runtime ya instalado en la raíz principal. |
| `python -m mypy --cache-dir=nul src/umbral/application/scoring/narrative.py src/umbral/infrastructure/scoring/narrative.py src/umbral/application/scoring/service.py` | **PASS**, 3 fuentes. |
| Mismo mypy más `tests/unit/application/scoring tests/unit/infrastructure/scoring/test_narrative_writer.py tests/contract/test_explanation_narrative.py tests/contract/test_explanation_endpoints.py` | **FAIL**, 18 errores en 3 archivos; 17 nuevos, 1 previo. |
| `python -m ruff check --no-cache <Python de git diff --name-only 72ebf51 f5adc16>` | **FAIL**, 8 E501; 1 nuevo, 7 previos. |
| `git diff --check 72ebf51 f5adc16`; `git diff --check` | **PASS**; advertencia de normalización LF/CRLF del informe de revisión previo, sin errores de whitespace. |
| `python -m pytest -p no:cacheprovider tests/unit tests/contract -q` | **Sin resultado concluyente**: se interrumpió después de varios minutos sin salida. No se contabiliza como pass ni como regresión. Se completaron luego los grupos adyacentes explícitos de arriba. |

Los primeros intentos de typecheck mediante npm con argumentos adicionales y rutas locales de `tsc` fallaron por resolución/invocación (`EUNKNOWNCONFIG` / `MODULE_NOT_FOUND`). La invocación final con ruta resuelta y sin escritura incremental pasó. No son errores del código.

### Probes independientes ejecutados por stdin

Se utilizó `python -` con `runpy.run_path` para reutilizar fixtures existentes, sin crear archivos. Reproducción mínima del bypass managed:

```python
import runpy
from dataclasses import replace

m = runpy.run_path('tests/unit/infrastructure/scoring/test_narrative_writer.py')
context = m['context'].__wrapped__()
gateway = m['ScriptedGateway']()
writer = m['_writer'](gateway)
gateway.output = {
    'text': 'No encaja por la buena conectividad.',
    'used_criteria': ['acceso_transporte'],
    'used_evidence_refs': ['urban:transit-1'],
}
assert writer.write(context).source == 'managed'  # defecto reproducido

context = replace(
    context,
    price_changes=({'field': 'price', 'before': 900,
                    'after': 800, 'currency': 'USD'},),
    allowed_evidence_refs=(*context.allowed_evidence_refs, 'listing_field:price'),
)
gateway.output = {
    'text': 'Encaja por la buena conectividad. Subió de USD 800 a USD 900.',
    'used_criteria': ['acceso_transporte'],
    'used_evidence_refs': ['urban:transit-1', 'listing_field:price'],
}
assert writer.write(context).source == 'managed'  # invierte la transición
```

Además se ejecutaron: los otros tres outputs de la tabla de Major 1; proyección geográfica de conteo cero generado por `UrbanSignalCalculator(load_urban_contract_published())`; mismatch de subte a 2.000 m; contributors extraídos de las fórmulas de v2 para parques/servicios/comercio; y scoring→explanation→fallback con luminosidad negativa y observación `0.1`. Los resultados concretos están documentados en Major 1–4. Estos son probes que revelan fallas, no nuevos tests aprobados de aceptación.

## Limitaciones

- No se ejecutó navegador/Preview, build de Next, proveedor LLM real, tests de integración con DB/Docker ni el harness completo. El typecheck y la suite de componentes/BFF no sustituyen esos checks.
- La corrida amplia de unit/contract interrumpida no permite afirmar que toda la suite backend pase. Sí terminaron y pasaron los 340 tests focalizados y adyacentes detallados.
- El comportamiento managed se ejercitó con gateway controlado: demuestra qué contenido acepta el validator, no la frecuencia con que un proveedor real produciría cada output.
- No identifiqué una regresión adicional de hard filters/ranking/notificaciones en las superficies revisadas y probadas. No afirmo igualdad de scores con `72ebf51`: activación y renormalización cambian deliberadamente por el contrato original.
- Los hallazgos de UI Minor 1–3 se apoyan en el contrato y flujo de código; no fueron reproducidos manualmente en navegador. Las fallas backend Major 1–4 sí tienen probes ejecutados, y los fallos de checks tienen salida fresca.
- El review cubre todo el cambio hasta `f5adc16`, no solo el último hardening. Ninguno de los errores previos de mypy/ruff se presenta como introducido por esta rama.

## Whole-branch correction round

The implementation was extended after this review. All five Major and four
Minor findings are resolved without changing scoring formulas, ranking, hard
filters, activation, notifications, database models, migrations, or LLM
decision behavior.

### Resolutions

- Major 1: the managed writer now builds typed packet-backed claims and accepts
  only deterministic sentence rendering for the exact submitted criteria and
  refs. Negations, mixed match/trade-off placement, inverted price transitions,
  and declared-but-unrendered refs fall back.
- Major 2: geographic facts carry observed value/unit and signal direction.
  Zero counts are omitted; far transport/café/service/commercial distances are
  not favorable matches; published v2 categories are recognized.
- Major 3: negative semantic matches preserve their observed direction in the
  fallback packet, including low luminosity as `poca luz natural`.
- Major 4: contributor matching follows the published v2 identities:
  `green_space`, `supermarket`, `pharmacy`, `convenience`, `health`,
  `restaurant`, `cafe`, and `shopping_mall`.
- Major 5: the two introduced scoring test typing failures are fixed with local
  annotations; no broad ignore was added.
- Minor 1: UI caveats no longer infer more nightlife or claim that the listing
  omitted unknown data when the payload does not provide that cause.
- Minor 2: deterministic explanation fallback text now uses human labels for
  supported concepts instead of `este criterio`.
- Minor 3: selecting the same listing/run preserves its loaded narrative; a
  regression test covers same-identity preservation and changed-identity reset.
- Minor 4: the introduced radar-service E501 was corrected locally. Seven older
  E501s in that service remain documented baseline findings.

### Fresh correction-round results

- Managed writer: `23 passed` after the five RED regressions.
- Focused narrative/geography/scoring/contracts: `179 passed, 11 warnings`.
- Adjacent backend groups: `185 passed`.
- Web: `32 files / 83 tests passed`; TypeScript typecheck passed.
- Targeted strict mypy over changed source/tests: passed with no errors.
- Ruff: only the seven pre-existing radar-service E501s remain.
- `git diff --check`: passed.

The packet correction was committed as `205b90c` (`fix: scope narrative copy to
submitted packets`) and the whole-branch correction as `e9004c2` (`fix: harden
narrative semantics and geographic context`). The accompanying report update is
committed after them. The broader full-repository pytest/mypy baseline remains
intentionally unclaimed.
