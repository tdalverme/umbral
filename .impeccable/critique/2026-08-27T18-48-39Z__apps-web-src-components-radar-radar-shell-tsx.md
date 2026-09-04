---
target: radar, mapa y chat copilot
total_score: 15
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
timestamp: 2026-08-27T18-48-39Z
slug: apps-web-src-components-radar-radar-shell-tsx
---
# Critique: radar-shell.tsx — Umbral Radar/Mápa/Chat

## Design Health Score
| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 1 | Sin freshness/stale, mapa sin skeleton, filtros sin aria-live |
| 2 | Match System / Real World | 2 | IDs crudos y source_id en lista, léxico no CABA |
| 3 | User Control and Freedom | 1 | Colapsos crípticos, chat collapsed tapa mapa, sin Esc global |
| 4 | Consistency and Standards | 2 | Opacidad mapa divergente 0.92 vs 0.82, layout max-w-5xl vs full-bleed |
| 5 | Error Prevention | 1 | Concat listingId sin validar, NaN budget, tabs con 0 sin warning |
| 6 | Recognition Rather Than Recall | 1 | 8 cards clónicas solo barrio·precio, sidebar colapsado solo inicial |
| 7 | Flexibility and Efficiency | 1 | Hidden en mobile xl, tabs sin handler, slice(0,8)+Cargar más descolocado |
| 8 | Aesthetic and Minimalist Design | 3 | Luz serena bien ejecutada pero 4 paneles fijos saturan en 1280 |
| 9 | Error Recovery | 2 | Vacíos con calma bien, errores crudos radar.error |
| 10 | Help and Documentation | 1 | Sin explicación curadas/snapshot, Tool jerga expuesta |
| **Total** | | **15/40** | **Poor** |

## Design Specificity Verdict
**LLM assessment**: 5/10 Umbral, 9/10 Luz serena. Tokens correctos (bosque/lino/terracota) pero placeholder `Por qué encaja: cercanía` idéntico en 8 cards destruye promesa de radar vivo con evidencia+confianza+snapshot versionado (PRODUCT.md). Sistema intercambiable con cualquier proptech mapa+lista+chat hasta cablear ReasonsStrip/EvidenceBadge reales.

**Deterministic scan**: 4 advisories (design-system-font-size 3× 11px en radar-chat-panel.tsx:25,32 y opportunity-detail-sheet.tsx:58; design-system-radius 1× 0.375rem en globals.css:106). 0 warnings/errors. --no-design-system 0 confirma drift solo de sistema de diseño.

**Visual overlays**: No disponible — devServer no corre (context-signals.mjs running:false, puertos 3000/4321/5173 cerrados), live-server.mjs --background no invocado. Fallback static only.

## Overall Impression
Shell luminoso y token-clean pero vacío de evidencia. Calma cromática no compensa 8 oportunidades indistinguibles. Mobile roto y sin feedback soft/hard rompen alivio.

## What's Working
1. Fundación Luz serena impecable — globals.css color-mix + layout next/font swap + mapa lino/terracota logra luminosa contenida sin frialdad startup.
2. Sincronía hover/selección mapa<->lista (hoverId/selectedId + case Terracota 10px) reduce búsqueda visual.
3. Voz y vacíos serenos (Probá ajustar radar en el chat, Escribile a Umbral) voseo sin FOMO.

## Priority Issues
P0 Shell mobile, P1 Placeholder, P1 Sobrecarga 11 opciones, P1 Acciones sin feedback, P2 Lenguaje técnico.

## Persona Red Flags
Sam ansiosa — Snapshot sha256 + 8 idénticas abandona. Valentina mobile — tabs falsos hidden. Martín presupuesto — mismo ruido que portales.

## Minor Observations
- filtered slice(0,8) antes de filtro saved puede dar 0
- »/« sin aria-label
- Composer bloqueado en waiting_decision impide editar
- Ir a lo más reciente siempre visible

## Questions to Consider
- Qué pasa si 8 curadas es mentira con datos faltantes?
- Cómo se siente Luz serena en Samsung A32 con reduced-motion?
- Por qué evidence vive fuera del shell móvil?
