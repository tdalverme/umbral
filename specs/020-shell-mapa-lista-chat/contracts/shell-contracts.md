# Contracts — Shell

## URL Query (shallow, no reload)
- `?listingId=<uuid>` — single-select oportunidad; si ausente, sin selección; al cerrar sheet se borra el param (shallow `router.replace`)
- `?filter=<all|saved|dismissed>` — filtro lista; default `all`; alias legacy `/radar/[id]/shortlist → ?filter=saved` y `dismissed → ?filter=dismissed`
- Ej: `/radar/abc-123?listingId=def-456&filter=saved`

## API ya existente (consumo sin cambios)
- `GET /radar/profiles` → `SearchProfile[]` alimenta sidebar
- `GET /radar/profiles/[id]/matches` → oportunidades curadas (max 8)
- `GET /listings/[id]` + `GET /radar/profiles/[id]/explanations/[listingId]` → detalle sheet
- `GET /urban/signals?listingId=` → `count_300m/600m + distance_nearest` + `snapshot {sha256, date}` + `signal_version`
- `POST /radar/chat/sessions` (lazy por search_profile_id) + `GET /resume` + `POST /runs/[runId]/decision` para HITL soft/hard

## Map style contract
- Fork `map-style-luz-serena.json` (desaturado): background `var(--brand-linen)` `#F4EFE6`, roads `var(--brand-forest)`/`var(--brand-sand)`, superficies `var(--brand-ivory)`, pins `forest` default / `terracotta #DE6D4A` selected
- `attributionControl: false` — crédito solo via `GlobalAttribution`

## Component props (UI)
- `RadarSidebar { radars, selectedId, collapsed, onSelect, onCreate, onRename }`
- `FloatingList { opportunities, selectedId, hoverId, filter, onSelect, onHover }`
- `OpportunityDetailSheet { opportunity, signals, onClose, onSave, onDismiss, onFeedback }`
- `MapLuzSerena { opportunities, selectedId, hoverId, onSelect }` emite `onViewportChange` solo por tool
