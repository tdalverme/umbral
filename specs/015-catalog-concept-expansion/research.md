# Research: Expansión del catálogo de conceptos (Fase 3)

**Date**: 2026-08-12

## Brainstorming — ideas, gaps y formas de implementación

### Ideas de conceptos para la beta

| Concepto | Tipo | Fuente | Proxy / decisión | Dificultad |
|---|---|---|---|---|
| `moderno` | Modelo cualitativo | descripción/amenities | enum `clasico\|renovado\|moderno` | Baja (plantilla luminosidad) |
| `proximidad_cafes` | Señal urbana | urban_signals cafe | cantidad en radio X (versionado) | Media (canal nuevo) |
| `acceso_transporte` | Señal urbana | urban_signals transport | presencia en radio X | Media (mismo canal) |
| `espacios_verdes` | Señal urbana | urban_signals green_space | presencia en radio X | Media (mismo canal) |
| `tranquilidad` | Modelo cualitativo | descripción | enum | Baja pero golden difícil (subjetivo) |
| `vistas` | Modelo cualitativo | descripción | enum | Baja pero evidencia débil |
| `subte_D` | Filtro espacial (NO concepto) | geometría de línea | distancia a la línea | Alta — fuera de alcance |

No perseguir en V1: calidad percibida ("lindos", "vistas lindas"), ruido (sin fuente), seguridad de datos (sin datos). Cada concepto subjetivo nuevo exige etiquetado — el límite real.

### Gaps identificados en el pipeline actual

- **G1 — El peso del fact no viaja en la compilación**: `CompiledCriterion` (criteria/contracts.py) no tiene weight; el engine toma el weight del policy estático. Un fact de un concepto fuera del policy (tipo_cocina, o cualquier concepto nuevo) puntuaría con peso 0 → la preferencia no mueve el ranking. **Bloqueante.**
- **G2 — Las señales urbanas no llegan al scoring**: `urban_signals` es una tabla aparte con geometría/payload; el scoring consume `listing_observations`. No hay canal urban → observación. **Bloqueante para cafés/transporte.**
- **G3 — Sin golden de extracción**: la extracción de modelos cualitativos no tiene gate de calidad por concepto; una regresión pasaría silenciosa. **Bloqueante para robustez.**
- **G4 — El threshold del evaluador semantic (0.5) es global**: luminosidad/estado/moderno comparten threshold; puede necesitarse calibración por concepto (declarable en `params_schema`).
- **G5 — El vocabulario canónico del chat crece por contrato, pero el intent compiler debe mantener ejemplos**: al agregar "moderno"/"cafés", conviene sumar ejemplos al prompt para que el modelo extraiga `preferencia=moderno` (bajo costo, parte del contrato).
- **G6 — Recomputación al agregar un concepto nuevo**: `_extraction_targets` usa `concepts_seed` (scope full) — un concepto nuevo se extrae en el próximo scope full ✓; la invalidación selectiva por concepto ya existe ✓. Falta un disparo explícito "extraer solo el concepto nuevo" (recompute con scope concept ya lo permite).
- **G7 — Costo de modelo por concepto cualitativo**: cada cualitativo agrega una llamada por listing; batch/rate limits ya existen (`qualitative_max_attempts`, batch_size). Monitorear tokens por concepto.
- **G8 — El proxy urbano necesita evidencia legible**: la observación urbana debe citar las señales (ids + `algorithm_version`) para que la explicación sea auditable.
- **G9 — Contradicción entre concepto y perfil duro**: p.ej. "no me gustan los pisos bajos" (fact piso) vs perfil duro sin piso — conviven sin conflicto hoy (el fact se suma), pero conviene documentar la precedencia (fact suave suma, no reemplaza hard filters).
- **G10 — Calidad del modelo sin datos reales etiquetados**: el golden inicial de "moderno" será sintético; calibrar con uso real (feedback/explicaciones vistas) antes de confiar en él.

### Formas de implementación evaluadas

**F1 — Weight del fact (G1):**
- (a) Agregar `weight: float` a `CompiledCriterion` + contrato `compilation-v1.json`; el compile lo toma del fact; el engine usa `criterion.weight` (del policy para fijos, del hecho para facts). Cambio de contrato acotado.
- (b) El engine busca el fact por concept_key para el weight → acopla el engine a los facts (peor, rompe pureza).
- **Decisión: (a)** — el criterio compilado es la unidad completa (params + weight), el engine queda puro.

**F2 — Canal urbano (G2):**
- (a) **Consolidación en observaciones** (`source = urban`): un paso de extracción que lee señales versionadas y produce `ListingObservation` (valor = conteo/bin por proxy; score del conteo; evidencia = señales citadas). El scoring/explicación no cambian (mismo canal). El proxy vive en `params_schema` del concepto. Invalidación por versión de concepto/extracción ya funciona.
- (b) Evaluador geo que consulta `urban_signals` directo en el engine → segundo canal de datos en el engine (rompe "el engine consume observaciones").
- (c) Vector de features por conteos → embeddings (prohibido).
- **Decisión: (a)** — el engine no cambia; la consolidación es código nuevo acotado en el servicio de criteria (tipo `urban` en `_extraction_targets`/`_extract_concept`).

**F3 — Matcher del concepto urbano:**
- (a) `numeric_range` existente con `min` del proxy (valor = cantidad de señales): reusa el evaluador; el proxy radio se usa en la consolidación, el umbral `min` en el evaluador. **Menos código nuevo.**
- (b) Matcher nuevo `urban_proximity` con evaluador propio (distancia real): más potente (distancia al más cercano) pero más código + calibración.
- **Decisión: (a) para V1** (cantidad en radio con `numeric_range` y `min` del proxy); (b) queda como mejora si la data de uso lo pide.

**F4 — Proxy versionado:**
- (a) En `params_schema` del concepto (radio, umbral) — una sola fuente, versionado con el concepto, invalidación automática al cambiar versión.
- (b) Contrato aparte `urban-proxy-v1.json`.
- **Decisión: (a)** — menos superficie; el radio del proxy alimenta la consolidación y el `min` al evaluador.

**F5 — Golden de extracción (G3):**
- (a) Fixture por concepto (proyección permitida → valor esperado) + gate en el harness (precision/recall sobre un set etiquetado sintético inicial).
- (b) Solo fixtures de humo (un caso por valor del enum) — más débil.
- **Decisión: (a)** — casos por valor del enum + casos negativos/ambiguos; umbral declarado en el contrato del golden; corre en `check-criteria.ps1`.

**F6 — Vocabulario del chat:**
- Entradas nuevas en `preferences-vocabulary-v1.json` ("moderno" → moderno; "cerca de cafés"/"con cafés cerca" → proximidad_cafes) + ejemplos en el intent compiler. Zero código en tools.

**F7 — Secuencia de entrega:**
1. Fundación (G1 + F2 + F3 + F5): la infraestructura que hace "solo datos".
2. Caso cualitativo "moderno" (valida el ciclo completo barato).
3. Caso urbano "proximidad_cafes" (valida el canal nuevo).
4. "acceso_transporte" (replica el ciclo urbano).
5. Golden + evals del chat para los tres.

## Decisiones de diseño

### D-01: El criterio compilado lleva el weight del hecho (F1-a)
- **Decision**: `CompiledCriterion.weight: float` — el compile lo setea desde `PreferenceFact.weight`; el engine usa el weight del criterio compilado cuando el concepto tiene fact, con fallback al policy.
- **Rationale**: el criterio compilado es la unidad completa y auditable; el engine sigue puro (no consulta facts).
- **Alternatives**: (b) el engine busca el fact — acopla y rompe pureza.

### D-02: Las señales urbanas se consolidan en observaciones (F2-a)
- **Decision**: paso de consolidación `urban` en el servicio de criteria que produce `ListingObservation(source="urban")` con el proxy del concepto y evidencia = señales citadas (id + algorithm_version). El engine no cambia.
- **Rationale**: un solo canal de observaciones para el scoring y las explicaciones; la invalidación selectiva existente cubre los cambios de proxy.
- **Alternatives**: (b) segundo canal en el engine — rompe el contrato del engine; (c) embeddings — prohibido.

### D-03: Matcher `numeric_range` con proxy en `params_schema` (F3-a/F4-a)
- **Decision**: V1 de proximidad = cantidad de señales en radio X; el valor observado es el conteo; el evaluador `numeric_range` usa `min` (umbral del proxy). El radio vive en `params_schema` del concepto.
- **Rationale**: reusa el evaluador existente; el proxy es explícito y versionado; la distancia real (matcher nuevo) queda como mejora condicional.
- **Alternatives**: (b) matcher `urban_proximity` con distancia — más potente, más calibración, sin necesidad demostrada.

### D-04: "Moderno" como modelo cualitativo (plantilla luminosidad)
- **Decision**: concepto `moderno` con `source: model`, schema enum `clasico|renovado|moderno`, evidencia + confianza; score derivado del enum (posicional, ya implementado).
- **Rationale**: el pipeline cualitativo ya está completo y validado (hallazgo de Fase 2 arreglado).
- **Alternatives**: regla por keywords — frágil y sin escala.

### D-05: Transporte V1 genérico, sin línea específica
- **Decision**: concepto `acceso_transporte` (señales transport en radio); subte D queda fuera (filtro espacial con geometría de línea, PostGIS — se justifica solo con data de uso).
- **Rationale**: el genérico cubre la mayoría de las preferencias expresables; la línea específica es un proyecto espacial aparte.

### D-06: Golden de extracción con umbral por concepto (F5-a)
- **Decision**: contrato `extraction-goldens-v1.json` (o por concepto en el seed) con casos etiquetados y umbral; el harness corre el gate y bloquea la publicación si falla.
- **Rationale**: hace la flexibilidad robusta: "solo datos" con verificación automática.
- **Alternatives**: (b) solo humo — no detecta regresiones.

## Costos y límites honestos

- El cuello de botella es el etiquetado: cada modelo cualitativo nuevo necesita un golden con casos reales para confiar; el sintético inicial solo gatea la mecánica.
- El proxy de cafés ("cantidad en radio") no captura calidad; se declara la limitación en la explicación ("basado en X cafés en un radio de Y").
- Los conceptos subjetivos (tranquilidad, vistas) tienen evidencia débil en el texto — no entrar sin fuente de datos.
- Costo de modelo: +1 llamada por listing por concepto cualitativo — monitorear en la extracción.
