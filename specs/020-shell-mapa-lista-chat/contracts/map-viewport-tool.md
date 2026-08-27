# Tool — update_map_viewport

Nombre: `update_map_viewport`
Origen: Agent Orchestrator (LangGraph) — tool explícita permissionada, no SQL libre

## Input
```json
{
  "center": [ -58.3816, -34.6037 ],
  "zoom": 16,
  "reason": "Centrando cerca de subte D por tu preferencia"
}
```
- `center` [lng, lat] requerido
- `zoom` int 10–18, default 14
- `reason` string auditable, mostrado en `stream-status` del chat

## Efecto
- Valida que no muta criterios/profiles
- Emite evento `map:flyTo` con `duration 900`, `easing` sereno; si `prefers-reduced-motion: reduce` → `jumpTo`
- Chat muestra reasoning antes de mover; usuario puede deshacer (limpia selección) o cerrar sheet
- No persistido en DB; viewport local no se guarda

## Tests
- Unit: tool no cambia `search_profile`
- Shell integration: enviar tool mueve pin selected y chat muestra reason
