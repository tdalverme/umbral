# Research — Shell Umbral mapa+lista+chat

**Fecha:** 2026-08-27 | **Fase:** 0 — todas las clarificaciones resueltas vía grilling Q1→Q18, sin NEEDS CLARIFICATION pendientes.

## Resumen de Decisiones

| Tema | Decisión | Racional | Alternativas descartadas |
|------|----------|----------|--------------------------|
| Identidad radar↔chat | 1:1 estricto `search_profile_id` = sidebar item = chat session = URL `/radar/[id]` lazy | Simplicidad, deeplink, back/forward, evita forks multi-hilo prematuros | 1:N hilos por radar, session global no scopeada |
| Shell 3 columnas | ≥1280 push 280/ flexible/ 400; 1024-1279 der overlay; <1024 ambos drawers, centro full. Rail 64 colapsado izq | Máxima legibilidad mapa sin header global, respeta calma | Header global fijo, 3 columnas siempre visibles <1024 (aplastado) |
| Mapa vs lista | Mapa full-bleed + lista flotante izq 320px scroll, no split 45/55 | Contexto geográfico siempre visible, patrón Milan desaturado | Split rígido tipo REALL, lista paginada 547 |
| Curaduría | Max 8 oportunidades curadas con razón, `Cargar más` auditado futuro | Prioriza relevancia sobre cantidad (brand) | Infinite scroll, paginación numérica |
| Detalle | Sheet 380px dentro de main (no modal), lista permanece debajo, `flyTo` zoom 16 | No mata mapa, mantiene comparación visual | Modal centrado, reuse panel chat der |
| Pin selección | Single-select `?listingId` shallow; hover 1.1+ring bosque, selected terracotta relleno; offset espiral 12px si colisión <30px, sin cluster | URL deeplink, terracota= oportunidad, sin pérdida de conteo | Multi-select + cluster, pin default forest siempre |
| Comparación | Deferred fuera de V1 | Reduce alcance, un solo foco | Checkbox multi + `/compare` sheet en V1 |
| Chat scope | 100% por radar, lazy session, reasoning/HITL vía ai-elements dentro del stream | Traza clara, no contamina mapa | Chat global, HITL overlay sobre mapa |
| Tool mapa | `update_map_viewport {center, zoom, reason}` auditable, `flyTo` 900ms ease, nunca muta hard filters sin HITL | Tool explícita, animación serena, control usuario | Agent mueve criterios directamente, `jump` sin razón |
| Estilo mapa | Fork `geo-map-style` playground desaturado: lino `#F4EFE6` fondo, bosque `#293F38` calles, arena `#D9C59F` secundaria, marfil `#FFFAF2` superficies, terracota `#DE6D4A` solo pins | Luz serena, tokens existentes, contraste AA | Mapbox default colorido, dark mode mapa negro, vector DB separada |
| Mobile | Tabs `Mapa|Lista|Chat` + drawer radares; default Lista si <5 else Mapa; bottom-sheet drag phase 2 | Evita mapa vacío, drawer familiar ChatGPT | Tabs no fijas, single page scroll |
| Señales urbanas | Reales vía contrato + snapshot SHA-256, al menos 1 categoría real (transporte) + mocks gris para resto, atribución solo `GlobalAttribution` | Reproducibilidad, ODbL compliance | Live OSM sin versión, atribución duplicada |
| Señales faltantes | `unknown` → `no sabemos` + punto para consultar, no bloquea ranking | Honestidad, `CONTEXT:hipótesis ≠ preferencia` | Inventar dato, filtrar |
| Tipografía/marca | `next/font` Fraunces `--font-brand` solo logo/headings breves, DM Sans `--font-sans` UI/body; shadcn semánticos (`bg-primary` etc.) nunca brand crudo | Fundaciones ya instaladas | Fraunces en tablas, terracotta como error |
| Migración rutas | `/radar` → redirect `/` con sidebar; `/radar/new` → Dialog; `shortlist/dismissed` → filtros `?filter=` con alias legacy; `compare` 404 controlado | No rompe e2e/colección Playwright | Páginas separadas legacy, nuevo router |
| Vacío/carga/error | Skeleton 3 cards + Spinner `role=status` no bloqueante; fallo snapshot → mapa base + señales unknown + Alert | Calma + próximo paso sin FOMO | Vacío con pressure, bloqueo ranking |
| A11y/foco | Landmarks `nav[Radares]/main[Mapa]/aside[Conversación]`, `skip-link`, `prefers-reduced-motion`→`jumpTo`, focus a `h2` sheet + `Esc` retorno, `--ring` derivado | `check-web` + axe 0 violaciones serias | Sin landmarks, foco perdido, animación siempre |
| Notifs | Bell mock con badge + link `/notifications` legacy, sin push/fatiga/horario en V1 | Prohibición brand sin control | Notifs proactivas sin fatiga |
| Performance | Sin virtualización para 8, `isStyleLoaded` guards, `once('load')`/`on('sourcedata')` ya probados | Reusa `geo-map-style` helpers | Virtualización prematura, tiles sin cache |

## Hallazgos por Tecnología

**MapLibre 6.2 + helpers playground**
- `scheduleSelectedFeaturePaint(map, id)` y `scheduleCategoryPaint(map, cats)` ya esperan `isStyleLoaded` y suscriben `once('load')` antes de `setPaintProperty`; `scheduleFeatureSourceData` espera `sourcedata`. Validado en `src/components/playground/geo-map-style.test.ts:1`. Reusar idéntico patrón para pin terracota y desaturado.

**shadcn/ui + Tailwind 4 + Luz serena**
- Tokens `--brand-*` ya en `globals.css` y mapeados a semánticos; `@theme inline` expone `--font-sans/brand`. Primitivas consumen `bg-primary` etc. — no duplicar colores. Validado por `brand-foundations.test.ts` y `foundation.test.tsx`.

**ai-elements + use-chat-stream**
- `chat-panel.test` + `stream-status.test` + `use-chat-stream.test` validan streaming, resume y decisions. HITL via `proposal-card`/`mini-card` ya existe; reusar dentro de `radar-chat-panel`.

**nuqs / useSearchParams**
- Para `?listingId` shallow sin reload: `next/navigation useSearchParams/useRouter` es suficiente sin añadir dependencia si se evita historial profundo; `nuqs` solo si se necesita parsing tipado — decisión defer hasta implementación (ambas válidas, no bloquea).

**Playwright + axe-core**
- `web-foundation.spec.ts` ya corre `axe` light/dark + reflow 320 + reduced-motion. Extender con caso shell sin añadir config.

## Riesgos Detectados

- Tiles OSM snapshot SHA mismatch → fallback mapa base + unknown (mitigado).
- Colisión pins a 8 con espiral → test visual en 320/768/1440 (mitigado).
- `DM_Sans`/`Fraunces` mock en vitest ya aliasado a `src/test/mocks/next-font-google.ts` (mitigado).
