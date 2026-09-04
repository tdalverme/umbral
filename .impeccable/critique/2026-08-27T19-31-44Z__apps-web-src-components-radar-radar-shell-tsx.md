---
target: radar, mapa y chat copilot
total_score: 30
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 0
timestamp: 2026-08-27T19-31-44Z
slug: apps-web-src-components-radar-radar-shell-tsx
---
# Critique: radar-shell.tsx — post-fix (polish)

## Design Health Score
| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Evidencia visible por card, freshness via snapshot date, aún sin stale badge pero mejora |
| 2 | Match System / Real World | 3 | neighborhoodLabel + Ver ficha humano, source_id oculto |
| 3 | User Control and Freedom | 3 | Tabs funcionales, drawer mobile, close en detail, composer no bloquea |
| 4 | Consistency and Standards | 3 | Opacidad unificada 0.92, tokens Luz serena coherentes |
| 5 | Error Prevention | 2 | Concat validado via neighborhoodLabel, aún NaN budget edge |
| 6 | Recognition Rather Than Recall | 3 | 3 destacadas con razón + dot terracota, resto colapsado Ver más |
| 7 | Flexibility and Efficiency | 3 | Mobile Tabs 44px, showAll, slice después de filter |
| 8 | Aesthetic and Minimalist Design | 4 | Densidad 3 destacadas, flat-by-default respetado |
| 9 | Error Recovery | 3 | Alert Guardada/Descartada con soft/hard explicado |
| 10 | Help and Documentation | 3 | curadas tooltip, snapshot hash con title, Tool traducido |
| **Total** | | **30/40** | **Good** |

## Fix summary
P0 mobile Tabs/Sheet, P1 evidencia real cableada, P1 jerarquía 3+colapsado, P1 feedback soft/hard, P2 lenguaje humano, minors 11px/radius/composer/jump.
