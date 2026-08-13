# Quickstart: Criterios suaves activos y chat de preferencias

**Date**: 2026-08-12

Guía de validación end-to-end del incremento. Detalles de implementación en `tasks.md`; entidades en `data-model.md`; vocabulario en `contracts/preferences-vocabulary-v1.json`.

## Evidencia de validación local (2026-08-12, stack real con modelo gpt-4.1-mini)

Validado de punta a punta contra Postgres/Redis locales (Docker Compose), API `dev_main`, worker RQ y gateway de modelo en `:8010`:

| Paso | Resultado |
|---|---|
| `scripts/seed-local.py` | 7 conceptos, 10 extraction_versions, 60 observaciones, 5 listings Silver; idempotente |
| Radar + run | 2 matches con score; `criterion_evaluations` por criterio |
| Chat "quiero un depto luminoso" | intent refinamiento → `propose_search_preference_update` → interrupt `proposal_decision` (kind preference, diff luminosidad/positive) |
| Approve | `preference_facts` activo (balcon/positive), recompute; el run nuevo rankea con contributions de conceptos (balcon, luminosidad, estado_general) |
| "¿qué preferencias tengo?" | `list_search_preferences` → respuesta con la preferencia vigente |
| "quitá la preferencia de balcón" | `propose_search_preference_removal` (diff `operation: remove`) → approve → fact `superseded` + propuesta `confirmed` |
| Errores guiados | `preference.not_active` → ofrece listar vigentes; contradicción → pregunta antes de aplicar |

Bugs reales encontrados y corregidos durante la validación: `compose.yaml` con password rechazado por pglayers; `dev_main` sin el stack del agente (chat 500); enum `actor_kind` sin `"user"` (migración `0014_actor_kind_user`) que rompía chat/feedback también en producción; handler de errores sin logging.

## Fase 2 — Loop de aprendizaje por feedback (extensión post-014)

Validado en vivo: `dislike + razón` ("poca luz") → señales del concepto → con `min_signals` alcanzadas se crea la `learning_proposal` → el grafo dispara el **interrupt automático** (0 LLM en surfcear) → approve → `preference_fact` + recompute → el reply del modelo queda grounded ("ajusté la búsqueda para priorizar la luminosidad").

- Tool `propose_learning_confirmation` (13 herramientas publicadas): surfcea una learning proposal pendiente por su id.
- Normalización determinística de razones: labels naturales ("poca luz") → claves canónicas (`lighting_bad`) antes de la validación del contrato.
- UI: el mini-card del chat tiene botones "Me gusta / No me gusta" con razones rápidas que envían el feedback al chat.
- `min_signals: 2` en la política publicada: Umbral propone aprender tras 2 señales consistentes del mismo concepto (beta con poco feedback).
- Hallazgo de calibración: el evaluador de `luminosidad` no discrimina observaciones baja/alta con polarity negative en el dataset demo — backlog de scoring.

## Prerrequisitos

- Postgres local con migraciones al head (`alembic upgrade head`).
- `.env.local` con la API key del modelo (extracción cualitativa) — si no está, los conceptos cualitativos quedan `failed` con código y las reglas igual publican (la validación de reglas no requiere modelo).
- Workers/API levantados con el stack v3 (patrón de los incrementos previos).

## 1. Activar la capa suave (Fase 0)

```powershell
$env:DATABASE_URL = "postgresql+psycopg://umbral:local@localhost:5432/umbral"
.venv\Scripts\python.exe scripts\seed-local.py
```

El seed (extendido) debe: sembrar `concepts` + `concept_versions` + `extraction_versions` (idempotente), correr la extracción sobre los listings demo y publicar `listing_observations` con evidencia (reglas siempre; cualitativos con el extractor fake determinístico si no hay modelo configurado, o con el provider managed si `EXTRACTION_PROVIDER=managed` y las claves están en `.env.local`). El radar se crea desde la UI (como hoy) y su run dispara la compilación con criterios suaves.

**Verificación** (consulta a la DB):

| Tabla | Esperado |
|---|---|
| `concepts` | 7 filas del catálogo (`concepts-v1`) |
| `extraction_versions` | ≥ 1 por artefacto (rule + model) |
| `listing_observations` | ≥ 1 por listing para conceptos por regla; cualitativos active si el modelo responde |
| `recommendation_runs` | 1 run `succeeded` con items |
| `criterion_evaluations` | filas con `criterion_key` de conceptos suaves |

**Validación de explicaciones**: `GET /search-profiles/{id}/matches` → items con score; `explain_match` (o endpoint de explicación) devuelve reasons con `evidence` no vacía cuando la observación existe.

**Reproducibilidad (SC-004)**: correr el seed dos veces → mismos counts, 0 duplicados (idempotencia por claves únicas activas).

## 2. Preferencia suave desde el chat (Fase 1)

Requisitos previos: seed del paso 1 + sesión de chat activa.

1. En el chat: `quiero un depto luminoso`.
   - Esperado: el agente propone un cambio de preferencia sobre `luminosidad`/positive, con diff visible (`Preferencia: Luminosidad`, `Sentido: Me gusta`) y **sin aplicar nada** (`learning_proposals` con state `pending`).
2. Confirmar en el interrupt (ProposalCard).
   - Esperado: `preference_facts` con `fact_source = chat`, `polarity = positive`; nuevo run disparado; el ranking del perfil cambia según política.
3. `no me gustan los deptos oscuros` → propuesta `luminosidad`/negative; si hay fact vigente de luminosidad, el impacto marca `contradicts` y el agente pregunta cómo dejar la preferencia antes de aplicar (FR-009).
4. `quiero algo con balcón` → propuesta `balcon`/positive; confirmar; el fact queda con fuente `chat`.
5. `quiero una cocina separada` → propuesta `tipo_cocina`/positive/`separada`.
6. Rechazo accionable: `quiero algo cerca del subte` → el agente explica que ese criterio no existe y ofrece el vocabulario soportado (0 invención).
7. `¿qué preferencias tengo?` → el agente lista las vigentes con `list_search_preferences` (concepto, sentido, fuente, fecha).
8. `saca la preferencia de luminosidad` → propuesta de remoción ("Quitar preferencia de tu radar") → confirmar → el fact queda `superseded` con trazabilidad y el siguiente run no la considera.
9. `saca la preferencia de cocina` sin aclarar integrada/separada → el agente pide el valor (`preference.value_required`).

**Verificación**: `learning_proposals` y `preference_facts` con trazabilidad (fuente, correlation_id, versión de perfil aplicada); `recommendation_runs` nuevo referenciando el fact.

## 3. Harness y tests

```powershell
.\scripts\check.ps1
```

Los checks de agent/criteria/chat deben pasar; los contract tests validan: contrato de tools v2 (nueva tool), intent schema v3 (refinamiento), vocabulario de preferencias, traducción canónica (unit), HITL preferencia en grafo v3, y evals golden con casos de preferencia (`run-real-evals.ps1` cuando haya endpoint de modelo real).

## Fuera de alcance (Fases 3/4)

- Nuevos conceptos (moderno, cafés, transporte) — ver `unsupported_notes` del vocabulario.
- Embeddings y urban signals.
- Notificaciones proactivas.
