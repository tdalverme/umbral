# AGENTS.md

## Proyecto
Umbral es un radar personal de vivienda: ayuda a crear busquedas activas, monitorea listings, aprende preferencias y recomienda oportunidades con razones claras. El chat es interfaz para expresar intencion y refinar criterios; la fuente de verdad del producto son busquedas, perfiles, listings, recomendaciones, feedback y eventos auditables.

## Criterios de trabajo
- Estas pautas priorizan cautela sobre velocidad; para tareas triviales, usar criterio.
- Antes de implementar, declarar supuestos, alternativas y tradeoffs relevantes.
- Si algo es ambiguo o riesgoso, frenar, nombrar la duda y preguntar.
- Preferir el minimo codigo que resuelve el problema; nada especulativo.
- No agregar features, abstracciones, configurabilidad ni manejo de errores no pedidos.
- Hacer cambios quirurgicos: tocar solo lo necesario y respetar el estilo existente.
- No refactorizar, borrar dead code ni reformatear zonas ajenas al pedido.
- Limpiar solo imports, variables o funciones que la propia modificacion deje huerfanos.
- Convertir tareas en objetivos verificables y cerrar el loop con tests o checks.
- Para cambios de varios pasos, indicar plan breve con verificacion por paso.

## Stack previsto
- Backend: Python + FastAPI, Pydantic, SQLAlchemy 2 y Alembic.
- Frontend: Next.js App Router, TypeScript, shadcn/ui, Tailwind, TanStack Query y MapLibre.
- Datos: Postgres con PostGIS y pgvector.
- Jobs: workers asincronicos con scheduler simple al inicio; Dagster/Prefect si hacen falta lineage y backfills.
- IA: LangGraph con checkpointer Postgres, structured outputs y tools internas explicitas.
- Infra: Redis para cache/queue, object storage para snapshots crudos, OpenTelemetry y Sentry.

## Comandos de ejecucion
- Activar entorno local: `.venv\Scripts\Activate.ps1`
- API de desarrollo: `uvicorn umbral.api.main:app --reload`
- Workers: `python -m umbral.workers`
- Tests: `pytest`
- Frontend, si existe app web: `npm run dev`
- Build frontend, si existe app web: `npm run build`
- Spec Kit: `.venv\Scripts\specify.exe check`; usar skills `$speckit-*`.
- Harness local: `.\scripts\check.ps1`
- Si un comando aun no existe en el repo, documentar la brecha en vez de crear wrappers vacios.

## Arquitectura
- Direccion de dependencias: UI -> Product API -> capa de aplicacion -> dominio/contratos.
- Infraestructura depende de puertos del dominio o aplicacion; el dominio no depende de FastAPI, DB, LLM, workers ni UI.
- El Agent Orchestrator solo llama tools internas explicitas; no accede libremente a la base ni decide rankings por si mismo.
- El Scoring Engine es puro, deterministico, versionado y testeable; consume features, criterios y observaciones ya estructuradas.
- La arquitectura de datos sigue Bronze -> Silver -> Gold: snapshots crudos, entidades normalizadas/deduplicadas, features/scores/recomendaciones.
- RAG y embeddings recuperan contexto; hard filters, ranking final y notificaciones los decide codigo auditable.
- Las explicaciones deben citar evidencia interna, version de scoring, snapshot de perfil y datos usados cuando aplique.

## Patrones prohibidos
- Ranking final decidido por respuestas generativas del LLM.
- SQL libre o acceso irrestricto a DB desde el agente.
- Listings que existen solo en el chat y no como objetos persistentes.
- Dedupe destructivo sin trazabilidad ni confianza.
- Microservicios, Kafka o vector DB separada para una V1 sin necesidad concreta.
- Prompts, modelos, scores o extracciones sin versionar.
- Embeddings usados como reemplazo de filtros duros.
- Notificaciones sin control de fatiga, horario, duplicados y razon auditable.
- Cambios amplios o refactors no pedidos.

## Errores Comunes

## Agent skills

### Issue tracker

Issues and specs live in GitHub Issues for this repository. See `docs/agents/issue-tracker.md`.

### Triage labels

Use the default Matt Pocock triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository: use the root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.
