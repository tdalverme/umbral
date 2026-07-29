# Umbral Beta Backlog Design

Fecha: 2026-07-28

Estado: aprobado

## Objetivo

Definir un backlog integral, trazable y ejecutable para llevar Umbral desde su
estado documental actual hasta una beta privada en produccion para alquileres
residenciales en CABA. El backlog debe preservar la vision de radar personal:
el chat interpreta y opera, mientras busquedas, listings, recomendaciones,
feedback y notificaciones persistentes son la fuente de verdad.

El backlog ejecutable termina en una beta operable y medible. La adquisicion
automatizada de listings, la publicacion directa, la expansion geografica y la
monetizacion quedan en un roadmap posterior explicito.

## Decisiones aprobadas

- Mercado inicial: alquiler residencial en CABA.
- Acceso: beta privada por invitacion y magic link.
- Fuente de listings de beta: importacion controlada por CSV, JSON o feed
  autorizado. El scraping no forma parte del camino critico.
- Canales de beta: centro de notificaciones web y email.
- Frontend: Next.js App Router, TypeScript, shadcn/ui, Tailwind, TanStack Query
  y MapLibre.
- Backend: monolito modular con Python, FastAPI, Pydantic, SQLAlchemy 2 y
  Alembic.
- Datos: Postgres con PostGIS y pgvector; Redis para cola, cache e
  idempotencia; object storage para snapshots y assets.
- Agente: LangGraph con checkpoints persistentes, tools internas explicitas y
  confirmacion humana para cambios ambiguos o sensibles.
- Matching y notificaciones: codigo deterministico, puro, versionado y
  auditable. El LLM no decide el ranking final.
- Criterio primario de beta: precision percibida de las recomendaciones
  notificadas.

## Alternativas consideradas

### Backlog por capas tecnicas

Ordenar datos, dominio, API, agente, frontend y operacion de manera horizontal
facilita la coordinacion tecnica, pero posterga demasiado la validacion con
usuarios y produce largos periodos sin un flujo completo demostrable.

### Backlog solo por historias verticales

Entregar crear radar, ver matches, dar feedback y recibir alertas maximiza la
velocidad de aprendizaje, pero puede duplicar fundamentos y dejar los riesgos
de datos, auditoria y operacion para demasiado tarde.

### Backlog hibrido por hitos

Es la opcion elegida. Construye una base minima auditable y luego entrega
incrementos verticales utilizables. Producto, datos/cumplimiento y
confiabilidad avanzan como tracks paralelos. Cada hito tiene una puerta de
salida verificable.

## Jerarquia del backlog

1. Un **hito** expresa un resultado de producto demostrable.
2. Una **epica** agrupa una capacidad completa necesaria para ese resultado.
3. Una **historia** entrega valor verificable a usuario, operador o equipo.
4. Las **tareas tecnicas** se derivan despues en un `tasks.md` de Spec Kit por
   incremento implementable, con archivos y checks concretos.

El backlog maestro no reemplaza los artefactos por feature. Cada incremento
debe seguir `spec.md` -> `plan.md` -> `tasks.md`; no se generara un unico
`tasks.md` para todo el producto.

## Secuencia de hitos

### H0 - Definicion de beta

Cerrar propuesta de valor, journey, taxonomia de criterios, politica de
evidencia, estrategia de datos, cumplimiento, privacidad y medicion. La salida
es un charter aprobado, contratos de datos definidos y un dataset controlado.

### H1 - Fundacion ejecutable

Crear el monolito modular, frontend, persistencia, workers, storage,
autenticacion, observabilidad, ambientes y gates de calidad. La salida es un
usuario invitado autenticado contra una aplicacion desplegada y observable.

### H2 - Primer radar de punta a punta

Importar listings controlados, preservar Bronze, normalizar Silver, crear una
busqueda, ejecutar filtros y scoring baseline, y visualizar matches
persistentes. La salida es un flujo operador -> importacion -> radar de usuario.

### H3 - Matching explicable y feedback

Agregar criterios blandos, observaciones con evidencia, scoring versionado,
recommendation runs, explicaciones, shortlist y feedback auditable. La salida
es una recomendacion completamente reconstruible.

### H4 - Radar conversacional

Incorporar LangGraph, tools explicitas, streaming, compilacion de preferencias,
explicaciones, comparaciones, confirmacion y deshacer. La salida es un chat que
opera el radar sin convertirse en fuente de verdad ni decidir scores.

### H5 - Proactividad controlada

Implementar notification planner, inbox web, email, outbox, horarios,
frecuencia, agrupacion, deduplicacion y fatiga. La salida es una alerta
deterministica, explicada, idempotente y respetuosa de preferencias.

### H6 - Beta privada

Completar onboarding, operacion, calidad de datos, soporte, privacidad,
seguridad, accesibilidad, performance, backups, dashboards y playbooks. La
salida es una beta operable con criterios de continuidad medibles.

## Arquitectura

Las dependencias fluyen de Product UI a Product API, capa de aplicacion y
dominio. Infraestructura implementa interfaces definidas hacia adentro. Los
modulos principales son:

- identidad y acceso;
- perfiles y criterios de busqueda;
- catalogo e ingestion Bronze/Silver/Gold;
- scoring y matching;
- recomendaciones, evidencia y explicaciones;
- feedback y aprendizaje controlado;
- conversaciones y orquestacion;
- planificacion y entrega de notificaciones;
- auditoria, metricas y operacion.

Cada modulo debe ser profundo: una interfaz pequena concentra comportamiento y
es tambien su superficie de prueba. Solo se crea un seam cuando existen al
menos dos adapters justificados, normalmente produccion y prueba.

Interfaces de referencia:

```text
ImportSource -> lote crudo + reporte de ingestion
CompileSearchProfile -> criterios ejecutables versionados
GenerateRecommendations -> recommendation run auditable
ExplainRecommendation -> evidencia + incertidumbre
RecordFeedback -> evento + propuesta reversible de aprendizaje
RunConversation -> respuesta + acciones estructuradas
PlanNotifications -> decisiones deterministicas de envio
DeliverNotification -> resultado idempotente
```

## Frontend

Next.js App Router permite combinar layouts y superficies renderizadas en
servidor con Client Components para mapa, chat, filtros y feedback. FastAPI
continua siendo la Product API y fuente de contratos. TanStack Query administra
estado servidor en las islas interactivas.

shadcn/ui se usa como codigo fuente del sistema visual. El backlog exige
componer primitives existentes, usar colores semanticos, estados accesibles y
patrones propios de formularios, overlays, empty states, loading y chat.

## LangGraph

LangGraph administra el estado de ejecucion conversacional, checkpoints,
reanudacion, streaming e interrupciones humanas. No guarda el estado de
producto como unica fuente de verdad. Los nodos llaman casos de uso mediante
tools con permisos acotados y nunca acceden libremente a Postgres.

El checkpointer de produccion usa Postgres. Cada tool mutante es idempotente y
cada run registra version de grafo, modelo, prompt, inputs permitidos,
resultados, errores y tiempos. Ranking y notificaciones quedan fuera del grafo.

## Manejo de fallos

- Los registros invalidos se ponen en cuarentena sin abortar el lote completo.
- La ausencia de evidencia baja confianza y no se interpreta como senal
  negativa.
- Un recommendation run no se publica parcialmente.
- LangGraph reanuda desde checkpoints y no repite efectos mutantes.
- Notificaciones usan outbox, reintentos acotados y deduplicacion.
- La UI distingue carga, vacio, datos incompletos, error recuperable y error
  bloqueante.

## Metricas de beta

Metrica principal:

```text
precision_percibida =
  recomendaciones notificadas y vistas con save/like/contacted dentro de 7 dias
  / recomendaciones notificadas y vistas
```

Objetivo inicial: al menos 35%.

Guardrails:

- como maximo 15% de recomendaciones notificadas y vistas marcadas como
  irrelevantes;
- cero alertas que violen filtros duros;
- cero notificaciones duplicadas;
- 100% de recomendaciones con perfil, listing, scoring y evidencia trazables;
- 100% de notificaciones con decision y razon auditables;
- al menos 70% de usuarios activados crean un radar y evaluan cinco propiedades
  durante su primera semana.

Los umbrales se pueden recalibrar despues de dos semanas. Las definiciones y
los eventos no cambian retroactivamente.

## Estrategia de verificacion

- tests unitarios y golden cases para scoring, filtros y notification planner;
- tests de contrato para HTTP, tools y adapters;
- integracion real con Postgres/PostGIS/pgvector, Redis y object storage;
- tests de calidad, cuarentena, dedupe y lineage;
- evals versionadas para extraccion, preferencias y explicaciones;
- Playwright para onboarding, radar, feedback, chat y alertas;
- checks de arquitectura para dependencias prohibidas;
- pruebas de permisos, rate limits, exportacion y borrado;
- smoke tests de despliegue, backup y restauracion.

Una historia no termina sin aceptacion, pruebas, telemetria, auditoria,
documentacion, accesibilidad aplicable y una migracion o rollback seguro.
`.\scripts\check.ps1` es el gate local comun.

## Roadmap posterior

1. Adquisicion automatizada mediante adapters de scraping o feeds, con
   monitoreo de cambios y revision legal por fuente.
2. Publicacion directa por inmobiliarias o propietarios, con identidad,
   moderacion, validacion, versionado y prevencion de fraude.
3. Profundidad de mercado: multiportal, dedupe avanzado, comparables,
   tendencias y calidad de fuentes.
4. Expansion: compra, GBA, mas canales y experiencia movil avanzada.
5. Negocio: monetizacion, billing, leads calificados y herramientas para
   brokers.

Scraper y publicacion directa son adapters distintos de la misma interfaz de
ingestion. Ninguno escribe directamente en Silver o Gold.

## Fuera de alcance de la beta

- scraping como dependencia operativa;
- publicacion abierta de propiedades;
- compra y GBA;
- WhatsApp, Telegram y push;
- microservicios, Kafka y vector DB separada;
- multi-agent y fine-tuning;
- billing y monetizacion;
- ranking o notificaciones decididos por generacion.

## Referencias

- [Next.js App Router](https://nextjs.org/docs/app)
- [shadcn/ui](https://ui.shadcn.com/docs)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Vision y arquitectura de producto](../../../vision-arquitectura-producto.md)
- [Constitucion de Umbral](../../../.specify/memory/constitution.md)
