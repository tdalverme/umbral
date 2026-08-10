# Agent Evals Contracts v1 (planning)

Contratos JSON maquina-comprobables que este incremento publica bajo
`contracts/agent-evals/v1/`:

| Archivo | Contenido | Validacion |
| --- | --- | --- |
| `conversations-golden-v1.json` | dataset golden de conversaciones (7 familias, >=3 casos por familia, expectativa de tools/confirmaciones/grounding/outcome) | `application/agent_evals/golden.py` + `tests/contract/test_agent_evals_golden.py` |
| `conversations-golden.schema.json` | JSON Schema con `registry_version` const | conformance (mismo archivo) |
| `graph-releases-v1.json` | registry append-only de releases del graph (componentes versionados, `affected_case_ids`, activacion auto/hibrida) | `application/agent_evals/releases.py` + `tests/contract/test_agent_evals_releases.py` |
| `price-table-v1.json` | precios por `model_version` (input/output por 1k tokens) | `application/agent_evals/price.py` + `tests/contract/test_agent_evals_price.py` |

## Golden dataset — forma de caso

```json
{
  "id": "conversation-001",
  "family": "onboarding",
  "context": { "profile": { "budget_max": 900000, "zone": "CABA" } },
  "turns": ["Quiero empezar a buscar un depto en CABA"],
  "expectation": {
    "tool_calls": [
      { "tool": "get_search_profile", "args": {}, "requires_confirmation": false, "order": 1 }
    ],
    "grounding": { "require_refs": false, "min_refs": 0, "declare_missing": false },
    "outcome": "completed"
  },
  "tags": ["onboarding"],
  "notes": "Caso base de onboarding con radar existente."
}
```

## Release — forma de entrada

```json
{
  "id": "graph-release-002",
  "components": {
    "prompt_versions": ["agent-reply-v2"],
    "model_version": "provider-x-model-y",
    "state_schema_version": "chat-state-v3",
    "topology_version": "chat-topology-v3",
    "intent_schema_version": "intent-schema-v3",
    "price_table_version": "price-table-v1",
    "touches_prompts_or_model": true
  },
  "owner": "team-agent",
  "justification": "Mejora de copy de grounding",
  "affected_case_ids": ["conversation-012"],
  "activation": {
    "status": "pending",
    "approved_by": null,
    "approval_evidence": null,
    "reverted_reason": null
  },
  "date": "2026-08-10"
}
```

Regla de activacion (Q6): si `touches_prompts_or_model` es true, la entrada
solo pasa a `active` con `approved_by` + `approval_evidence` (reporte de
eval); en caso contrario se activa automaticamente con gate verde.

## Eventos nuevos (events registry)

`agent.budget_warning.v1` (server, keys: session_id, ratio), `agent.budget_exhausted.v1` (server, keys: session_id, limit_kind), `agent.rate_limit_exceeded.v1` (server, keys: session_id, limit_kind). Sin PII (forbidden_keys del registry se aplican).

## Errores tipados nuevos

- `agent_evals.regression_blocked` — el gate bloquea la release (razones por caso, 0 PII).
- `agent.budget_exhausted` / `agent.budget_warning` / `agent.rate_limit_exceeded` — estados tipados y recuperables del contrato de chat (mapeo en el router).
