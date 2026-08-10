# Quickstart: Tools explicitas y permisos (H4.2)

**Feature**: 010-agent-tools | **Date**: 2026-08-09

Validation guide. Implementation details live in `plan.md` and `tasks.md`.

## Prerequisites

- `.venv` activado y `uv sync --frozen --all-groups`.
- Postgres con PostGIS/pgvector accesible para la integración (testcontainers
  según la convención de `check-agent.ps1`).
- Migración `0010_agent_tools` aplicada (tabla
  `search_profile_update_proposals` + enum `proposal_state`).

## Escenarios

### 1. Conformance: tool contract y schemas v2

```powershell
uv run pytest tests/contract/test_agent_tools_contract.py tests/contract/test_agent_state_schema_v2.py tests/contract/test_agent_graph_topology_v2.py tests/contract/test_agent_reply_schema_v2.py tests/contract/test_agent_tool_events.py -q
```

Expected: PASS. `tool-contract-v1.json` expone exactamente las 8 tools con
sus flags; los schemas v2 son JSON-safe y versionados
(`AGENT_TOOLS_STATE_SCHEMA_VERSION=2`, `AGENT_TOOLS_TOPOLOGY_VERSION=2`);
el registry de eventos acepta `search_profile.update_proposed.v1` /
`search_profile.update_applied.v1` y rechaza tipos desconocidos (FR-001,
FR-004, FR-005, DoD #4).

### 2. Ciclo de vida de propuestas: propose → confirm → apply

```powershell
uv run pytest tests/integration/agent/tools tests/unit/application/agent/tools -q
```

Expected: PASS. Con Postgres (testcontainers):

- `propose` produce diff validado + impacto y crea una propuesta `pending`
  durable con `base_profile_version`; el perfil NO cambia (FR-007/FR-008).
- `apply` con propuesta válida, `confirmation=true` e idempotency key:
  versiona el perfil (nueva versión, conservando las previas), emite
  `search_profile.update_applied.v1` y dispara recomputación que preserva el
  run anterior; la propuesta pasa a `approved` (FR-010/FR-011, H3-030).
- Replay con la MISMA idempotency key: 0 duplicados de versión/run/evento
  (FR-012).
- `apply` sin confirmación, con propuesta ajena, vencida, ya usada o con
  otra key: error tipado, 0 efectos (FR-010/FR-012).
- Obsolescencia: si el perfil cambió desde `base_profile_version`, apply
  rechaza la propuesta por obsolescencia con error tipado (clarificación
  Q1).
- El duty de vencimiento (`expire_search_profile_proposals`) marca las
  propuestas pendientes expiradas como `rejected('expired')` (FR-009).

### 3. Tools de lectura: perfil, matches, explicación, comparación

```powershell
uv run pytest tests/unit/agent/tools tests/unit/application/radar -q
```

Expected: PASS.

- `get_search_profile` devuelve solo el perfil de la sesión (snapshot +
  criterios ejecutables + estado); ids ajenos → denegado (FR-005/FR-006).
- `find_matches` devuelve items persistidos del último run publicado, con
  overlay de dismissed; sin run publicado o desactualizado → estado explícito
  (`run_id: null`, `stale`), 0 scores inventados y 0 recomputaciones
  (FR-013/FR-014).
- `explain_match` recupera la explicación persistida (score version,
  reasons, risks, missing_data, evidence refs) y declara faltantes; 0
  afirmaciones no soportadas (FR-015/FR-016).
- `compare_listings` valida pertenencia al radar y límite; 0 ganador
  generativo (FR-017/FR-018).

### 4. Feedback desde el chat

```powershell
uv run pytest tests/unit/agent/tools/test_record_feedback.py tests/unit/application/feedback -q
```

Expected: PASS.

- `record_feedback` con `like`/`dislike` (+ `reason_keys` opcionales):
  evento inmutable idempotente (repetir con la misma key → `noop: true`);
  cambiar decisión → supersede con compensación trazable (FR-019).
- Con señal suficiente según política, devuelve `learning_proposal_id`
  (propuesta pendiente, nunca aplicada automáticamente) (FR-020).
- `save`/`dismiss`/`contacted` desde el chat → rechazados con error tipado
  (clarificación Q3, FR-019).

### 5. Contexto urbano (P1)

```powershell
uv run pytest tests/unit/agent/tools/test_search_urban_context.py -q
```

Expected: PASS. `search_urban_context` devuelve solo signals versionadas
(fuente, fecha, algoritmo) y omite coordenadas cuando la precisión
autorizada no es `exact`/`block`; zona sin datos → declara ausencia, 0 datos
inventados (FR-021).

### 6. Suite de abuso (gate, UM-H4-016)

```powershell
uv run pytest tests/unit/agent/tools/test_abuse_suite.py -q
```

Expected: PASS (determinista, sin LLM). Acceso cruzado con ids manipulados
en las 8 tools → denegado en el 100% de los casos; args fuera de schema →
rechazo tipado con 0 efectos; prompt injection en args/contenido → 0 tools
no pedidas y 0 datos ajenos; solicitudes de volumen excesivo → salida
acotada por redacción; mutación sin confirmación → 0 efectos persistentes
(FR-022/FR-023).

### 7. Arquitectura y harness completo

```powershell
uv run pytest tests/architecture/test_agent_boundaries.py -q
.\scripts\check-agent-tools.ps1
.\scripts\check.ps1
```

Expected: PASS en los tres. `check-agent-tools.ps1` queda registrado en
`check.ps1` (FR-024, SC-010); el test de arquitectura verifica que la capa
`agent/tools` solo consume puertos de application (Principio III) y que 0
superficies HTTP/UI nuevas aparecen (FR-025).

## Verificación final

- Cerrar con `.\scripts\check.ps1` en verde desde checkout limpio y
  registrar evidencia consolidada en
  `docs/runbooks/evidence/agent-tools-acceptance.md` (DoD #9), incluyendo
  los 7 escenarios de este quickstart y el diff de
  `contracts/events/v1/events-registry.json`.
