# ADR 0001: Stack de aplicacion y agente

Fecha: 2026-07-28

Estado: aceptado

## Contexto

Umbral necesita una interfaz visual, geografica y conversacional sobre una
Product API Python. El radar, los detalles y la navegacion se benefician de
renderizado inicial en servidor; mapa, chat, filtros y feedback requieren alta
interactividad. El agente necesita estado durable, streaming, reanudacion y
confirmacion humana, sin convertirse en fuente de verdad ni decidir ranking.

## Decision

### Frontend

Usar Next.js App Router con TypeScript.

- Las rutas, layouts y superficies de lectura usan Server Components cuando
  resulte adecuado.
- Mapa, chat, filtros, formularios y feedback se implementan como Client
  Components acotados.
- FastAPI conserva los contratos de Product API.
- TanStack Query administra estado remoto en superficies interactivas.
- MapLibre implementa la experiencia geografica.

### Sistema visual

Usar shadcn/ui con Tailwind.

- Los componentes se agregan como codigo fuente del proyecto.
- Se componen primitives existentes antes de crear markup o abstracciones
  propias.
- Los estados visuales usan tokens semanticos y deben ser accesibles.
- Formularios, overlays, chat, loading, errores y empty states siguen las
  primitives y patrones de shadcn.

### Agente

Usar LangGraph en Python.

- El grafo orquesta interpretacion, aclaraciones, tools y redaccion.
- Un checkpointer Postgres persiste threads y permite reanudacion.
- Las interrupciones se usan para confirmar cambios ambiguos o sensibles.
- Las tools llaman interfaces explicitas de aplicacion y no acceden libremente
  a la base.
- Búsquedas, listings, recomendaciones, feedback y eventos persisten en el
  modelo de producto, no solo en checkpoints.
- Scoring y notification planning permanecen fuera del LLM y del grafo.

## Consecuencias

### Positivas

- Una sola aplicacion web soporta navegacion, renderizado inicial y
  interactividad compleja.
- shadcn reduce trabajo visual repetido sin ocultar el codigo del sistema de
  diseño.
- LangGraph aporta persistencia, reanudacion, streaming e human-in-the-loop
  para un flujo conversacional stateful.
- Los seams entre UI, Product API, tools y dominio permanecen testeables.

### Costos y riesgos

- Next.js exige decidir con cuidado que codigo corre en servidor o cliente.
- El codigo de shadcn pasa a ser responsabilidad del repositorio y debe
  revisarse al actualizarlo.
- LangGraph agrega estado operacional y migraciones de grafo/checkpoints.
- El equipo debe evitar modelar en el grafo datos que pertenecen al dominio.

## Alternativas rechazadas

### React con Vite

Es valido para una SPA, pero requiere sumar por separado convenciones de
routing, renderizado de servidor y autenticacion. No ofrece una ventaja clara
para el producto actual frente a Next.js.

### OpenAI Agents SDK o loop propio

Reducen abstraccion inicial, pero Umbral ya requiere checkpoints, reanudacion,
streaming e interrupciones humanas como capacidades deliberadas de la beta.

### Chat como fuente de verdad

Se rechaza porque impediria reconstruir decisiones, reutilizar listings fuera
de la conversacion y mantener un radar persistente.

## Referencias

- https://nextjs.org/docs/app
- https://ui.shadcn.com/docs
- https://docs.langchain.com/oss/python/langgraph/overview
- https://docs.langchain.com/oss/python/langgraph/persistence
