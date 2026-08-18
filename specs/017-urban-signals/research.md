# Research: Señales urbanas declarativas

## Resumen

La feature rediseña el contexto urbano del repo para que las preferencias de cercanía se computen desde datos abiertos de OpenStreetMap mediante un contrato declarativo y versionado. Las decisiones se tomaron en una sesión de grilling (2026-08-17) que partió de una POC previa en el repo `umbral-mvp` con import de `.osm.pbf` y cálculo de señales urbanas.

## Decisiones

### Decision 1 - Contrato declarativo y versionado

- **Decisión**: el conocimiento de dominio (mapping de tags, primitivas, señales, pesos, radios, targets) vive en un contrato JSON versionado, no en código. El contrato se registra como una `extraction_version` más, reutilizando el lineage existente.
- **Razón**: el repo prohíbe scoring sin versionar; el contrato hace que agregar una señal sea editar JSON, no escribir Python. El MVP tenía pesos hardcodeados en `UrbanSignalCalculator`, lo que violaría la constitución del repo.
- **Alternativas consideradas**: portar el calculator del MVP tal cual (rechazado por no versionado); código con constantes (rechazado por no auditable).

### Decision 2 - Señales factuales puras; el scoring decide la ponderación

- **Decisión**: el contrato declara señales del entorno del listing (factuales). Las preferencias del usuario ponderan esas señales en el scoring de cada radar. El contrato urbano NO declara pesos por preferencia.
- **Razón**: separa "el entorno es ruidoso" (factual, del listing) de "al usuario el ruido le importa" (preferencial, del radar). El MVP las mezclaba en `_urban_fit`.
- **Alternativas consideradas**: contrato con pesos por preferencia (rechazado por acoplar listing y radar).

### Decision 3 - Dos niveles de señales: base y compuestas

- **Decisión**: primitivas (hojas) → señales base (fórmulas sobre primitivas) → señales compuestas (fórmulas sobre señales base). `noise_risk` es compuesta de `nightlife_intensity`, `road_noise`, `rail_noise`.
- **Razón**: el MVP ya usa dos niveles; un solo nivel duplicaría fórmulas al componer.
- **Alternativas consideradas**: un solo nivel (rechazado por duplicación de fórmulas).

### Decision 4 - Normalización por barrio, selectiva por tipo de señal

- **Decisión**: las señales de densidad se normalizan por barrio (percentil); las de distancia a infraestructura mayor (subte, parque, hospital) permanecen absolutas. El modo se declara por señal en el contrato (`normalized_by: "barrio" | "absolute"`).
- **Razón**: OSM tiene cobertura desigual por barrio (Palermo mapeado, Lugano no); normalizar densidades elimina el sesgo. La infraestructura mayor está bien mapeada en todos lados; normalizarla destruiría significado absoluto.
- **Alternativas consideradas**: normalizar todo (destruye distancia absoluta); no normalizar (sesgo de mapeo contamina el ranking).

### Decision 5 - Fallback global decidido en el job de estadísticas

- **Decisión**: la tabla de estadísticas por barrio declara `normalization_scope: "barrio" | "caba"` según si `sample_size >= min_sample_per_barrio` (10). La decisión es estable entre batches y se toma en el job, no por listing.
- **Razón**: decidir por listing haría fluctuar la normalización; la tabla la fija por barrio y señal.
- **Alternativas consideradas**: fallback por listing (rechazado por inestable).

### Decision 6 - Crudo y normalizado por separado

- **Decisión**: cada señal persiste `value` (crudo) y `normalized_value` (para scoring). Las explicaciones citan los datos crudos; el scoring consume el normalizado.
- **Razón**: la explicación honesta ("5 cafes a 300m, alto en tu barrio") necesita el crudo; la comparación justa necesita el normalizado.
- **Alternativas consideradas**: solo normalizado (pierde evidencia).

### Decision 7 - Desconocimiento explícito y confidence declarada

- **Decisión**: el contrato declara un default global para missing (`value: null, confidence: 0.0`). La confidence se deriva con regla única global (`weighted_input_coverage` + `missing_penalty`): fracción de inputs con datos, penalizando missing. Los listings sin coordenadas precisas se excluyen de señales urbanas.
- **Razón**: el scoring no debe tratar "no sé" como valor real; la confidence viaja en la observación y el engine existente ya penaliza confidence baja.
- **Alternativas consideradas**: confidence por señal (verboso); confidence global del MVP (mezcla abundancia con confianza).

### Decision 8 - Fuente: Geofabrik Argentina

- **Decisión**: el snapshot proviene de `argentina-latest.osm.pbf` de Geofabrik (~427 MB, actualización diaria). El contrato declara la fuente.
- **Razón**: mismo pipeline que la POC validada; descarga directa sin esperar generación on-demand; 427 MB es manejable con osmium.
- **Alternativas consideradas**: BBBike CABA (más chico pero on-demand y depende de tercero); Overpass en vivo (rate limits, no determinista); Overpass batch (complejidad extra sin ganancia a 427 MB).

### Decision 9 - Descarga externa → object storage → import; un solo comando

- **Decisión**: el operador ejecuta un comando de ops que descarga, verifica hash y sube a object storage; el worker importa desde allí. El worker no depende de la red.
- **Razón**: reproducibilidad (el snapshot es un objeto versionado), resiliencia (Geofabrik caído no bloquea el import), coherente con el patrón de imports existente.
- **Alternativas consideradas**: descarga automática en el worker (dependencia de red en runtime).

### Decision 10 - Las señales se entregan como observaciones; el worker urbano las escribe

- **Decisión**: el worker urbano escribe directamente las `ListingObservation` de los concepts con `signal_ref`. El scoring no cambia.
- **Razón**: las señales son datos del listing (factuales, precomputadas para todos); la observación es el formato de entrega. El extractor de criterios no necesita cambios.
- **Alternativas consideradas**: el worker de criterios genera observaciones a demanda (depende de radares activos).

### Decision 11 - Matcher nuevo `signal_score`

- **Decisión**: las observaciones urbanas usan un matcher `signal_score` nuevo (evaluador puro que traspasa el score 0-1 con su confidence), declarado en el registry de matchers.
- **Razón**: el score ya está normalizado; `numeric_range` con `min:0, max:1` sería un uso forzado.
- **Alternativas consideradas**: reutilizar `numeric_range` (deshonesto semánticamente).

### Decision 12 - Atribución ODbL

- **Decisión**: el contrato declara `attribution` y `license`; el frontend muestra la atribución en una superficie global (footer o página de licencias). Las explicaciones de señales no citan OSM.
- **Razón**: ODbL exige atribución visible al usuario final; citarla en cada señal sería ruido.
- **Alternativas consideradas**: atribución solo en código (no cumple "reasonably calculated to make any Person aware").

### Decision 13 - Verificación por separado + puente en trayectorias

- **Decisión**: el pipeline urbano tiene suite propia (conformance del contrato + golden del calculator + integration con snapshot fixture). Las trayectorias v2 agregan un caso de puente que seedea una observación y verifica la vinculación del deseo, sin depender del import OSM.
- **Razón**: responsabilidades distintas (orchestrator vs scoring) y determinismo (golden con valores exactos vs fixture de datos).
- **Alternativas consideradas**: trayectorias con pipeline real (frágil y lento).
