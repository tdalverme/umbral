# Data Model — Shell Umbral mapa+lista+chat

**Entidades de UI (derivadas, no nuevas tablas DB):**

## Radar (search_profile)
- Campos: `search_profile_id` (PK, UUID), `name` (string editable), `status` (active|paused|archived), `zones` (neighbourhood labels), `budget_max`, `min_rooms`, `created_at`, `updated_at`
- Relaciones: 1 radar → N matches/oportunidades, 1 chat session, N explanations, N feedback events
- Validación: nombre ≥3 chars, `budget_max` >0, `zones` ≥1
- Estado: single-select en URL `?listingId` por radar, no ranking por agente

## Oportunidad (listing + match + explanation + señales urbanas)
- Campos: `listing_id`, `address`, `price_value`, `surface_m2`, `rooms`, `photos[ ]`, `match_reason` (coincidencias), `concessions[ ]`, `uncertainties[ ]` (unknown), `urban_signals: { category -> { count_300m, count_600m, distance_nearest } }` + `signal_version` + `snapshot { date, sha256 }`, `explanation_version`, `scoring_version`
- Relaciones: pertence a 1 radar (match), puede estar Guardada/Descartada (`?filter`)
- Validación: `unknown` cuando faltan datos nunca inventado; terracota nunca mapea a error; precio/sup no convertidos

## Pin de Mapa
- Campos: `listing_id`, `lng`, `lat`, `state` (default|hover|selected), `category_color` (forest default, terracota selected), `offset` (espiral 12px si colisión <30px)
- Fuente: derivado de Oportunidad + viewport; sin cluster para ≤8

## Viewport de Mapa
- Campos: `center [lng,lat]`, `zoom` (selected→16), `reason` (string auditable), `animated` (flyTo 900ms vs jumpTo si reduced-motion)
- Validación: tool `update_map_viewport` solo muta viewport, nunca criterios

## Filtro de Lista
- Campos: `filter` enum `all|saved|dismissed` mapeado a `?filter`, default `all`
- Relación: filtra oportunidades por estado sin nueva ruta

## Sesión de Chat por Radar
- Campos: `sessionId` (lazy por search_profile_id), `messages[]` (user/assistant + reasoning + HITL proposal-card/mini-card), `runId`, `learning-proposals` con `mode soft/hard` por concepto
- Validación: 1:1 radar↔session; historial persistido via `resume`; confirmación HITL requerida para elevar soft→hard

## Señal Urbana (urban signal)
- Campos: `category` (transporte/café/parque + escolar/deportivo/cultural/bici/salud), `primitive` (count_300/600, distance_nearest), `value`, `confidence`, `evidence`, `source`, `computed_version`
- Fuente: contrato versionado + snapshot inmutable OSM; cálculo Silver

## Transiciones relevantes
- Hover card/list → pin hover (ephemeral, no URL)
- Click card/pin → `?listingId` set → `flyTo` + `scheduleSelectedFeaturePaint(terracotta)` + scrollIntoView + focus sheet + `scheduleCategoryPaint` para desaturado
- Crear radar → `POST /radar/profiles` + lazy session + sidebar update
- `Guardar/Descartar` → actualiza `?filter` sin navegar
- Chat tool `update_map_viewport` → valida center/zoom + razón → anima mapa
