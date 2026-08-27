# Quickstart — Shell Umbral mapa+lista+chat

## Prerrequisitos
- `npm run dev` en `apps/web` (Next App Router)
- Postgres/PostGIS y API corriendo si se prueban datos reales; si no, mocks de `lib/radar/client` + snapshot SHA
- `GlobalAttribution` visible

## Validación manual (1 sola costura alta)
1. Entrar a `/radar` → redirect a `/` con sidebar Radares (≥1 radar). Sidebar muestra `nav[Radares]`, puede colapsar a rail 64.
2. Click radar A → URL `/radar/<id>` sin reload, `aside[Conversación]` carga historial scopeado (o bienvenida + chips).
3. Central: mapa full-bleed linen `#F4EFE6` + lista flotante 320px con max 8 cards ( `All | Guardadas | Descartadas` Tabs filtran `?filter`). Hover card → pin crece 1.1 + ring bosque.
4. Click card → `?listingId=<uuid>` en URL, `flyTo` 900ms a 16, sheet 380px abre dentro de main con foto→por qué→concesiones→incertidumbre→señales (al menos transporte real) → acciones; lista sigue debajo scroll visible. `Esc` cierra y devuelve foco a card.
5. En chat escribir "cerca de subte D" → reasoning visible → `update_map_viewport` con reason → mapa se mueve; `prefers-reduced-motion` hace `jumpTo`.
6. Mobile 375: tabs `Mapa|Lista|Chat` + drawer hamburguesa; default Lista si <5.

## Comandos de verificación
```powershell
npm --workspace @umbral/web run typecheck
npm --workspace @umbral/web run lint
npm --workspace @umbral/web run test -- src/app/(protected)/radar/shell.integration.test.tsx
npm --workspace @umbral/web run test -- src/app/brand-foundations.test.ts src/components/brand/logo-assets.test.ts src/components/brand/brand-logo.test.tsx
npm --workspace @umbral/web run build
# si hay datos: .\scripts\check-web.ps1  # debe reportar [PASS] Checks web (vitest/playwright collection) y 0 axe serias
```

## Esperado
- 0 violaciones axe serias/críticas en light/dark, reflow 320 sin overflow, skip-link funcional, foco programático correcto, terracota `#DE6D4A` solo en pins selected/hover, sin score numérico.
