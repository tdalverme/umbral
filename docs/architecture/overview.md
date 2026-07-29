# Architecture Overview

Umbral se organiza como un monolito modular con capas claras. La prioridad de la V1 es aprender rapido sin perder trazabilidad: cada recomendacion debe poder reconstruirse desde el perfil usado, el snapshot del listing, las features disponibles, la version de scoring y la evidencia citada.

## Foundation runtime implementado

La base ejecutable añade probes `/health`, `/ready`, `/version`, PostgreSQL y
Alembic con siete tablas, runtime de jobs at-least-once, object versions
inmutables, backup/restore beside-primary, señales metadata-only y gates de
manifest/promoción. Redis es transporte reconstruible; PostgreSQL y los
manifiestos son fuente de verdad operativa.

## Stack decidido para la beta

- Product UI: Next.js App Router, TypeScript, shadcn/ui, Tailwind, TanStack Query y MapLibre.
- Product API: Python, FastAPI, Pydantic, SQLAlchemy 2 y Alembic.
- Agente: LangGraph con checkpointer Postgres y tools internas explicitas.
- Datos: Postgres, PostGIS y pgvector; Redis para queue/cache/idempotencia; object storage para Bronze y media.
- Operacion: workers asincronicos, scheduler simple, OpenTelemetry y Sentry.

## Direccion de dependencias

```text
Product UI
  -> Product API
    -> Application services / agent tools
      -> Domain contracts and deterministic engines

Infrastructure adapters
  -> implementan puertos de application/domain
```

La dirección se verifica con Import Linter en `scripts/check-architecture.ps1`.

El dominio no debe importar FastAPI, clientes de LLM, SQLAlchemy, workers ni detalles de storage. La infraestructura implementa puertos para persistencia, retrieval, notificaciones, object storage, geocoding y observabilidad.

## Capas

| Capa | Responsabilidad | No debe hacer |
| --- | --- | --- |
| Product UI | Next.js App Router para radar, cards, mapa, shortlist, chat contextual y edicion del brief vivo; shadcn/ui compone el sistema visual. | Decidir ranking o guardar estado como unica fuente de verdad local. |
| Product API | Autenticacion, permisos, contratos HTTP, rate limits y coordinacion de casos de uso. | Contener reglas de matching profundas o acceder a fuentes externas sin servicio dedicado. |
| Application | Orquestar casos de uso: crear busqueda, actualizar perfil, buscar matches, registrar feedback, explicar y comparar. | Mezclar reglas de dominio con detalles de framework o DB. |
| Agent Orchestrator | LangGraph interpreta lenguaje natural, mantiene checkpoints de ejecucion, llama tools internas y redacta respuestas con evidencia. | Tener acceso libre a DB, usar checkpoints como fuente de verdad de producto o decidir scores finales por generacion. |
| Domain / Scoring | Aplicar filtros duros, evaluar criterios, calcular score, planificar notificaciones y producir explicaciones auditables. | Depender de LLM en tiempo de ranking. |
| Retrieval | Recuperar listings, evidencia, memoria de usuario, documentos y contexto de mercado. | Sustituir reglas deterministicas o hard filters. |
| Data Pipeline | Capturar, normalizar, deduplicar, enriquecer y versionar datos inmobiliarios y urbanos. | Fusionar datos destructivamente sin guardar snapshots y confianza. |
| Infrastructure | Postgres/PostGIS/pgvector, Redis, object storage, workers, schedulers, observabilidad y proveedores externos. | Filtrar logica de negocio hacia adaptadores. |

## Flujo de producto

```text
Usuario
  -> UI crea o edita una busqueda activa
  -> API ejecuta caso de uso
  -> Agent/Application compilan criterios estructurados
  -> Scoring Engine evalua candidatos
  -> API devuelve matches, explicaciones y acciones
  -> Feedback vuelve al perfil vivo y a recommendation runs
```

El chat maneja y explica el radar, pero el radar guarda y organiza las oportunidades. Todo listing mencionado por el agente debe existir como objeto persistente dentro de una busqueda activa.

LangGraph persiste estado conversacional y puede reanudar una ejecucion, pero sus nodos solo cruzan interfaces explicitas de aplicacion. Busquedas, listings, recommendation runs, feedback y notification events se guardan en el modelo de producto. Las tools mutantes son idempotentes y los cambios ambiguos o sensibles requieren confirmacion.

## Flujo de datos

```text
Fuentes
  -> Bronze: raw snapshots inmutables
  -> Silver: entidades normalizadas y deduplicadas
  -> Gold: features, observaciones, embeddings, scores y recomendaciones
  -> Product API / Scoring / Retrieval
```

Bronze preserva lo capturado para auditoria y reparsing. Silver consolida propiedades y versiones de listings. Gold agrega inteligencia util para producto: `listing_observations`, `profile_criteria`, `criterion_evaluations`, `recommendation_items`, `recommendation_explanations`, `feedback_events` y `notification_events`.

## Reglas de diseno

- El LLM interpreta intencion y extrae significado; el codigo deterministico decide ranking y notificaciones.
- Las tools del agente son contratos estables, testeables y con permisos acotados.
- Los graph runs, prompts, modelos, schemas y tool runs se versionan y correlacionan con los eventos de producto que producen.
- Cada feature cualitativa debe guardar valor, confianza, evidencia, fuente, version y fecha de calculo.
- Las notificaciones pasan por un planner que considera score minimo, novedad, fatiga, horario, canal y duplicados.
- La arquitectura puede crecer, pero la V1 debe evitar complejidad operacional que no mejore aprendizaje o confianza.
