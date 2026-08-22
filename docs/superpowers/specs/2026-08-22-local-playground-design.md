# Local Playground para Umbral

**Estado:** Diseño aprobado para revisión escrita  
**Fecha:** 2026-08-22

## Objetivo

Agregar una superficie local, visual e interactiva para probar rápidamente el
comportamiento del producto sin pasar por release, promote, la suite completa,
el harness ni migraciones de datos de producto.

El playground tendrá dos modos de trabajo:

1. **Conversation Lab:** ejecutar conversaciones reales o simuladas sobre
   fixtures aislados y observar respuesta, tools, estado del perfil y efectos.
2. **Geo Lab:** seleccionar un listing y explorar cómo sus POIs y features
   lineales producen primitivas, señales y contribuciones.

El playground es una herramienta de desarrollo local. No será una superficie
de producto, no tendrá multiusuario y no se expondrá en ambientes compartidos.

## Decisión de diseño

Usar una pequeña fachada de playground sobre los módulos reales del runtime,
con adapters locales en memoria y fixtures versionados. El graph conversacional,
el registro de tools, los contratos urbanos y el cálculo determinista siguen
siendo la fuente de verdad.

Esto evita dos extremos:

- levantar toda la operación durable para cada iteración manual;
- construir un simulador alternativo que pueda divergir del producto.

La seam principal será un módulo de aplicación local con una interfaz pequeña:

```text
run_conversation(scenario) -> conversation_trace
inspect_listing_geo(request) -> geo_inspection
```

La interfaz oculta la composición de sesiones, graph, gateways, recorder,
fixtures, repositorios locales y cálculo de evidencia. Los adapters concretos
podrán usar memoria, un gateway LLM real configurado localmente o un gateway
fake determinista.

## Alcance del MVP

### Conversation Lab

La pantalla tendrá tres zonas:

- **Configuración:** fixture de perfil/listing, modo de modelo, caso inicial y
  acciones de reset/replay.
- **Conversación:** mensajes del usuario y del asistente, con soporte para
  continuar el escenario de forma interactiva.
- **Inspector:** timeline de ejecución, tools, estado y métricas.

El inspector debe mostrar, por cada turno:

- mensaje de entrada y respuesta;
- estado del perfil antes y después;
- tools llamadas en orden;
- argumentos validados y resultados redacted;
- errores, confirmaciones y propuestas;
- referencias citadas por la respuesta;
- prompt/modelo/schema versions;
- latencia, tokens y costo estimado cuando exista tabla de precios.

El playground capturará prompts y resultados solamente en memoria durante la
sesión. No agregará tablas ni persistirá PII o trazas del playground en la base
de datos de producto.

### Geo Lab

La pantalla tendrá:

- mapa con el listing seleccionado;
- POIs y geometrías lineales dentro del radio elegido;
- controles de radio y snapshot/contrato cuando haya más de una opción local;
- panel de evidencia navegable.

El panel seguirá esta jerarquía:

```text
señal
  -> término de fórmula
    -> primitiva
      -> POI o feature lineal
```

Cada nivel debe mostrar sus valores relevantes:

- señal: valor normalizado, confianza, missing y contribución agregada;
- término: peso, operación, score del término y referencia usada;
- primitiva: categoría, métrica, radio y distancia/conteo;
- feature: categoría, geometría, distancia y referencia de origen.

También debe mostrar snapshot urbano, versión de contrato, barrio usado para
normalización y atribución de OpenStreetMap.

La UI debe distinguir `missing`, `NULL` y cero observado. Las features lineales
se deben mostrar como geometrías reales cuando existan, no como puntos
sintéticos.

## Escenarios y fixtures

Los escenarios serán archivos JSON locales dentro de una carpeta dedicada del
playground. El MVP no necesita editor genérico de JSON: la UI selecciona
fixtures existentes y permite escribir los turnos.

Un escenario contiene, como mínimo:

```json
{
  "id": "ambiguous-budget-change",
  "profile_fixture": "profile-caba-basic",
  "listing_fixture": "listing-palermo-001",
  "turns": [
    "Quiero algo más barato, pero no resigno luz"
  ],
  "assertions": [
    {"kind": "tool_called", "tool": "propose_search_profile_update"},
    {"kind": "no_unconfirmed_mutation"}
  ]
}
```

El runner debe crear una sesión y estado aislados por ejecución. Resetear el
escenario crea una ejecución nueva; no intenta revertir efectos en una base
compartida.

Los casos difíciles iniciales serán:

- cambio ambiguo de presupuesto o zona;
- preferencia contradictoria;
- propuesta que requiere confirmación;
- tool inválida o con error controlado;
- listing sin datos suficientes;
- referencia a un listing equivocado;
- datos urbanos faltantes;
- ubicación aproximada;
- POIs y features lineales cercanos.

El resultado de una ejecución se puede descargar como JSON para convertirlo
manualmente en fixture o caso dorado. No se construye aún un repositorio de
casos ni un motor de evals nuevo.

## Contratos de salida

### `conversation_trace`

El resultado contiene:

- `run_id` local;
- escenario y configuración usada;
- turns y respuestas;
- eventos ordenados;
- llamadas de modelo con versiones y usage;
- llamadas de tools con argumentos redacted, resultado redacted y status;
- snapshots de estado antes/después;
- propuestas y confirmaciones;
- assertions ejecutadas y veredictos;
- error tipado si la ejecución no termina.

El trace reutiliza las estructuras existentes de `GraphRun`, `NodeRun`,
`ModelCall` y los contratos de tools como evidencia base. El collector del
playground puede agregar detalles efímeros que hoy no se persisten, como el
contenido del prompt y los argumentos completos antes de redaction, siempre que
se mantengan dentro del proceso local.

### `geo_inspection`

El resultado contiene:

- listing y coordenadas disponibles, con su precisión;
- snapshot y contrato urbano;
- features cercanas serializables para el mapa;
- primitivas observadas;
- señales base y compuestas;
- contributors de cada señal;
- lineage y atribución;
- warnings de cobertura, geometría o datos faltantes.

La derivación de señales debe delegar en `UrbanSignalCalculator` y la lectura
de categorías/primitivas/señales debe pasar por ports existentes o adapters
locales equivalentes. No se implementará una segunda fórmula dentro del
frontend.

## Arquitectura local

### Backend

Agregar un módulo de aplicación de playground y un router dev-only.

- El router expone endpoints locales para listar fixtures, ejecutar/resumir
  una conversación y obtener la inspección geográfica.
- El router no contiene lógica de scoring, selección de tools ni cálculo
  urbano.
- El módulo se monta únicamente en la app local de desarrollo.
- La app productiva no registra ni sirve estos endpoints.

El stack conversacional local usará:

- `MemorySaver` o equivalente para el checkpointer;
- repositorios de sesión, mensajes y runs en memoria;
- `RunRecorder` en memoria que además alimente el collector;
- el `ToolRegistry`, `ToolExecutor` y graph actuales;
- gateway LLM real si está configurado, con gateway fake como modo
  determinista y para errores reproducibles;
- adapters locales de los servicios de radar, preferencias, feedback y
  criteria sobre los fixtures.

El stack no ejecutará scheduler, worker, relay de outbox ni notificaciones.
Las mutaciones del escenario afectan solamente el estado en memoria.

### Frontend

Agregar una ruta local única `/playground` con dos tabs. Reutilizar:

- componentes UI existentes;
- `MaplibreMap` para render de mapa;
- tipos y estilos del radar cuando ayuden a mantener consistencia;
- el patrón de cliente BFF existente.

El frontend no conocerá detalles de SQL, PostGIS, LangGraph ni contratos
internos. Recibirá los dos resultados serializados y los presentará como
timeline, diff y árbol de evidencia.

## Seguridad y límites

- La ruta y los endpoints se habilitan únicamente con un guard explícito de
  entorno local.
- No se usan cookies de usuario ni datos de usuarios reales en el MVP.
- Las tools mutantes corren sobre adapters en memoria.
- No se envían emails, notificaciones ni jobs.
- Los outputs visibles respetan la redaction del contrato de tools.
- Los prompts completos solo viven en memoria y no se escriben en logs.
- Si se habilita un gateway LLM real, la UI muestra que la ejecución tiene
  costo externo potencial.

## Manejo de errores

El playground debe mostrar errores recuperables dentro del trace, sin tumbar
la sesión completa:

- gateway no configurado: indicar cómo activar modo fake o real;
- tool inválida: mostrar validación y no aplicar efectos;
- tool fallida: conservar el turno y marcar la tool en rojo;
- fixture incompleto: indicar el campo faltante;
- listing sin coordenadas precisas: mostrar el listing, pero deshabilitar
  geometría de distancia y explicar la limitación;
- snapshot/contrato ausente: mostrar `missing` con lineage parcial.

## Verificación

La primera implementación se verificará con checks pequeños y enfocados:

1. Tests de contrato del runner: cada ejecución queda aislada y devuelve un
   trace serializable.
2. Tests del collector: orden de tools, redaction, model calls y diffs de
   estado.
3. Tests de assertions: llamadas esperadas, mutaciones confirmadas y
   referencias válidas.
4. Tests de Geo Lab: señales y contributors coinciden con
   `UrbanSignalCalculator`; `missing` no se convierte en cero.
5. Un smoke test local de la ruta `/playground` con fixtures fake.
6. Verificación manual de una conversación con LLM real y de un listing con
   POIs y una feature lineal.

No se agrega el playground al harness obligatorio ni a los gates de release.

## Orden de implementación

1. Contratos, fixtures mínimos y runner en memoria.
2. Collector de trace y endpoint de Conversation Lab.
3. UI de conversación con timeline, estado y replay/reset.
4. Servicio de Geo Lab y endpoint de inspección.
5. UI de mapa y árbol de evidencia.
6. Assertions básicas y export JSON.
7. Fixtures de casos difíciles y smoke test local.

## Criterios de aceptación

- Levantar el playground requiere un comando local dedicado, sin release,
  promote, worker, scheduler, suite completa ni harness.
- Un desarrollador puede ejecutar una conversación en menos de un minuto desde
  que abre la pantalla.
- Puede identificar qué tools se llamaron, con qué argumentos, en qué orden y
  con qué resultado.
- Puede ver exactamente qué cambió en el perfil y si hubo confirmación.
- Puede seleccionar un listing en el mapa y recorrer señal → primitiva →
  feature original.
- Puede diferenciar dato faltante de cero observado.
- Puede repetir el escenario sin contaminar otra ejecución.
- Una ejecución se puede exportar como JSON y reproducir con el mismo fixture.

## No objetivos

- ambiente compartido o multiusuario;
- persistencia de ejecuciones en producción;
- editor completo de prompts;
- comparación masiva de modelos/releases;
- dashboard histórico de costos o latencias;
- motor nuevo de evals;
- edición de snapshots OSM;
- ranking alternativo o fórmula urbana alternativa;
- notificaciones, emails o jobs reales;
- acceso arbitrario a SQL o a la base desde la UI.
