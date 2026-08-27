# Spec — Shell Umbral: mapa + lista + chat con fundaciones Luz serena

**Fecha:** 2026-08-27
**Estado:** listo para agente (`ready-for-agent`) — grilling cerrado Q1→Q18
**Base:** `2026-08-26-umbral-brand-system-design.md` + `docs/brand/visual-foundations.md` (geometría `balanced`, tokens Luz serena) + `CONTEXT.md` (radar, señales urbanas, snapshot)

## Problem Statement

Desde la perspectiva de quien busca vivienda con poco tiempo, hoy Umbral tiene el sistema de marca y los datos (radar versionado, oportunidades explicables, señales urbanas), pero la UI sigue fragmentada: `/radar` es lista vertical sin contexto geográfico, `/radar/[id]` muestra detalle tabulado, y el chat vive desacoplado. La persona debe alternar entre vistas para responder "¿dónde está esto?", "¿qué hay alrededor?", "¿por qué me lo muestran?" y "¿qué hago ahora?", perdiendo el principio "Tu próximo lugar se acerca" y la calma editorial.

El chat como única superficie no permite escanear pocas oportunidades con razones auditables, y el mapa como única superficie no explica coincidencias ni aprende preferencias suaves. Faltan el puente lista↔mapa y la conversación situada por radar que convierta intención en criterio ejecutable.

## Solution

Desde la perspectiva de la persona, un shell inspirado en ChatGPT con 3 regiones persistentes, centrado en un **mapa full-bleed como lienzo**:

- **Sidebar izquierda** (nav): lista de radares. 1 radar = 1 search_profile = 1 sesión de chat 1:1, nombre editable inline. Colapsable a rail 64px. En `<1280` centro priorizado, sidebar se oculta.
- **Panel central** (main): mapa MapLibre que ocupa todo el panel, con **lista flotante izquierda (320px)** superpuesta y scroll independiente. Muestra como máximo **8 oportunidades curadas** (no 547) con razón breve. Hover en card → pin crece 1.1 + ring bosque; click → selección single, `flyTo` al punto y apertura de **sheet detalle derecho (380px) dentro del mismo panel central** (no modal, lista permanece visible debajo). Al centrar, el mapa enfatiza primitivas urbanas (conteo 300/600m + distancia nearest) del snapshot/contrato vigente, resto atenuado.
- **Panel derecho** (complementary): conversación scopeada 100% al radar seleccionado, con historial persistido, reasoning steps y mini-cards HITL vía `ai-elements`. El agente no decide ranking; puede emitir tool explícito `update_map_viewport` (center/zoom/reason) que anima el mapa con `flyTo` 900ms; no muta filtros hard sin confirmación.

En mobile: tabs fijas `Mapa | Lista | Chat` + drawer hamburguesa para radares. Por defecto `Lista` si <5 oportunidades, `Mapa` si hay selección; bottom-sheet drag deja para fase 2. Estilo Luz serena (`#F4EFE6` lino fondo, `#293F38` bosque calles, `#D9C59F` arena secundaria, `#FFFAF2` marfil superficies, `#DE6D4A` terracota solo para pin seleccionado/hover/novedad). Fraunces solo para titular marca, DM Sans para UI. Foco gestionado con landmarks (`nav` Radares / `main` Mapa / `aside` Conversación), `skip-link` existente, contraste AA y `prefers-reduced-motion` respeta jump sin animación. Datos urbanos reales estilo playground (transporte/cafés/parques + nuevas categorías con contrato + hash SHA-256, atribución via `GlobalAttribution` existente).

## User Stories

### Sidebar Radares (1:1)
1. Como persona con varios radares, quiero ver todos mis radares en la barra izquierda, para elegir con un click cuál radar explorar.
2. Como persona, quiero que seleccionar un radar cambie la URL a `/radar/[id]` y mantenga el chat y el mapa scopeados a ese radar, para poder compartir el enlace y volver con back/forward.
3. Como persona, quiero editar el nombre del radar inline en el sidebar y que se refleje en el header del mapa, para reconocer búsquedas sin recordar IDs.
4. Como persona que apenas creó un radar sin mensajes, quiero que el radar ya aparezca en la lista y al seleccionarlo ver mapa vacío con CTA calmo, para no sentir que falta algo.
5. Como persona en desktop ≥1280, quiero ver los 3 paneles simultáneos push sin header global, para escanear lista, mapa y chat a la vez.
6. Como persona en 1024–1279, quiero que el chat derecho se vuelva overlay sobre el mapa, para que el centro siga siendo legible.
7. Como persona en <1024, quiero que ambos laterales sean drawers y el centro tome todo el ancho, para que el mapa no se aplaste.

### Panel Central — Mapa full-bleed + lista flotante
8. Como persona, quiero que el mapa ocupe todo el panel central y la lista sea una sheet flotante izquierda de 320px con scroll independiente, para mantener contexto geográfico siempre visible.
9. Como persona, quiero ver como máximo 8 oportunidades curadas con razón breve, no una paginación densa, para decidir sin ruido.
10. Como persona, quiero que hacer hover en una card resalte el pin correspondiente (escala 1.1 + ring bosque), para vincular lista y territorio.
11. Como persona, quiero que al clickear card u pin el mapa haga `flyTo` al punto (zoom 16) y abra un sheet detalle, sin tapar la lista, para comparar con el alrededor.
12. Como persona que mira densidad urbana, quiero que al centrar se resalten amenidades 300/600m y distancia nearest del contrato urbano (transporte, cafés, escuelas, etc.), y el resto se atenúe, para evaluar entorno sin inventar datos.
13. Como persona, quiero que si 2-3 pins colisionan a <30px el sistema los desplace en espiral 12px sin clusterizar, para no perder la cuenta de 8.
14. Como persona en mobile, quiero tabs `Mapa | Lista | Chat` fijas y que por defecto vea `Lista` si hay pocas oportunidades, para no enfrentar un mapa vacío.

### Sheet Detalle de Oportunidad
15. Como persona, quiero que el sheet detalle muestre en orden: foto+precio+dirección, Por qué encaja + por qué se muestra, concesiones, incertidumbres ("no sabemos"), señales urbanas con fuente/versión, y acciones Ver/Guardar/Descartar/Consultar, para decidir con razones auditables.
16. Como persona, quiero distinguir coincidencias, concesiones e incertidumbres sin score numérico, para no confundir ranking con certeza.
17. Como persona, quiero que terracota solo señale novedad/oportunidad y nunca error destructivo, para mantener la semántica de marca.
18. Como persona con teclado, quiero que al abrir el sheet el foco vaya a su `<h2>` (`tabIndex=-1` + focus) y `Esc` lo cierre devolviendo foco a la card, para no perder navegación.
19. Como persona, quiero dar feedback suave (reordena) o hard (excluye con confirmación) por concepto desde el detalle, para enseñar sin miedo a borrar demasiado.
20. Como persona, quiero que el sheet sea descartable solo cerrando el `?listingId` de la URL, para poder copiar el enlace profundo de una oportunidad.

### Chat Derecho Scopeado
21. Como persona, quiero que el chat derecho esté 100% atado al radar seleccionado con historial persistido y resume, para no mezclar intenciones entre búsquedas.
22. Como persona, quiero ver reasoning steps y proposals HITL dentro del stream de chat (ai-elements), no flotando sobre el mapa, para entender qué hace el agente sin perder el territorio.
23. Como persona, quiero que cuando digo "cerca de subte D" el agente pueda pedir mover el mapa (tool con reason visible), para que la acción sea auditable y reversible.
24. Como persona, quiero que el agente nunca reordene filtros hard sin mi confirmación, para mantener control.
25. Como persona con chat vacío, quiero ver prompt de bienvenida con_descriptor "Copiloto para encontrar tu próximo lugar" + chips ("Busco 2 amb en Palermo con balcón"), para empezar sin pantalla en blanco.
26. Como persona, quiero que el chat use DM Sans y el único Fraunces sea el logo/titular, para respetar la fundación tipográfica.

### Señales Urbanas y Datos Reales
27. Como persona, quiero que las señales urbanas provengan de snapshot inmutable con hash SHA-256 y contrato versionado, no de live OSM, para que el cálculo sea reproducible.
28. Como persona, quiero ver atribución ODbL solo en `GlobalAttribution` existente, sin duplicar control de MapLibre, para no contaminar el mapa calmo.
29. Como persona, quiero que si una señal falta, se muestre "no sabemos — punto para consultar" en lugar de inventar, para preservar honestidad.

### Accesibilidad y Marca
30. Como persona usuaria de teclado, quiero landmarks `nav[Radares] / main[Mapa de oportunidades] / complementary[Conversación del radar]` + `skip-link` existente, para navegar regiones sin ratón.
31. Como persona que activa `prefers-reduced-motion`, quiero que `flyTo` se convierta en `jumpTo` y se desactiven animaciones persistentes, para evitar mareo.
32. Como persona con daltonismo, quiero que toda combinación texto/fondo de este incremento mantenga WCAG AA y que terracota no sea único portador de información, para poder distinguir sin color.
33. Como persona, quiero que el favicon `/brand/umbral-favicon.svg` siga expuesto y que el shell nunca use colores brand crudos en clases de componentes (`bg-primary` etc.), para respetar tokens semánticos.

### Navegación Legacy
34. Como persona con bookmark a `/radar/new`, quiero que hoy abra un `Dialog` sobre el shell en lugar de navegación, para no perder el contexto del mapa.
35. Como persona que usaba `/radar/[id]/shortlist` y `dismissed`, quiero ver ahora filtros `Todos | Guardadas | Descartadas` dentro de la misma lista flotante, con las rutas viejas como alias `?filter=`, para no romper e2e.
36. Como persona que espera comparar, quiero saber que la comparación multi (max 3) queda deferred — en V1 solo selecciono una y la comparativa vendrá después, para no sobrecargar el shell.

## Implementation Decisions

- **Módulos a construir/modificar (sin paths, seams altos):** Shell de 3 regiones push (estado colapso por breakpoint 1280/1024), ListaFlotante, MapaLuzSerena (wrapper MapLibre), PinLayer (selección terracota vs bosque hover, offset espiral 12px, sin cluster), SheetDetalle (jerarquía foto→por qué→concesiones→incertidumbre→señales→acciones), ChatScopeado (wrapper sobre chat existente con session lazy por search_profile_id), HeaderShell (BrandLogo + bell mock), Store URL `?listingId` + `?filter` via searchParams (nuqs/useSearchParams) con hover ephemeral, Tool `update_map_viewport` y empatía minimal.
- **Interfaces modificadas:** `radarApi.listProfiles` alimenta sidebar; `radarApi matches/listings/explanations` + `urban/signals` alimentan mapa/lista/sheet; `chat/sessions` + `runs/[runId]/decision` + `learning-proposals` persisten conversación; `neighborhoodLabel` y contrato urbano (categorías OSM, primitivas 300/600, fórmulas) declaran fuentes.
- **Arquitectura y dirección de dependencias:** UI → Product API → aplicación → dominio/contratos; infra depende de puertos; Agent Orchestrator solo via tools explícitas, sin SQL libre ni ranking generativo; ScoringEngine puro y versionado no afectado; Bronze→Silver→Gold conserva snapshots crudos; embeddings/RAG solo recuperan contexto, no filtran.
- **Contratos API próximos:** `GET /radar/profiles`, `GET /radar/profiles/[id]/matches`, `GET /listings/[id] + explanations`, `GET /urban/signals?listingId=`, `POST /radar/chat/sessions` (lazy), `POST /runs/[runId]/decision` (confirm HITL), `POST update_map_viewport {center:[lng,lat],zoom,reason}` auditable; `?listingId` y `?filter` como query shallow, no rutas nuevas.
- **Decisiones técnicas:** Mapa full-bleed flex + lista 320px absolute + sheet detalle 380px dentro de main; hover local, selected en URL; `flyTo` 900ms ease (fallback `jumpTo` con reduced-motion); style MapLibre fork de playground desaturado con 4 brand hex + terracota solo pins; `attributionControl: false`; mobile tabs + drawer, phase 2 bottom-sheet; no vector DB separada, no microservicios.
- **Decisiones visuales:** shadcn semánticos (`bg-primary`/`text-muted-foreground`) con valores fuente brand; Fraunces only logo/headings breves, DM Sans UI/body; zona protección ¼ símbolo, mínimos 16px symbol/100px horizontal (visual-foundations); terracota ≠ destructive; Calma sin urgencias ni contadores falsos ni FOMO.
- **Esquema/cambios de datos:** Ninguna migración DB en este incremento; señales urbanas leen snapshot existente con `fecha/hash SHA-256`; aprendizaje confirma soft/hard via propuestas existentes, sin crear fuerza hard desde comportamiento pasivo.
- **Interacciones específicas:** Click card/pin → set `?listingId` → `flyTo` + `scheduleSelectedFeaturePaint` + `scheduleCategoryPaint` + scrollIntoView nearest + foco programático sheet; `Esc` limpia `?listingId` y retorna foco; hover → `scheduleSelectedFeaturePaint` escala; colisión espiral sin cluster.

Prototipo citado: schedule helpers de `geo-map-style.ts` (espera `isStyleLoaded` + `once('load')`/`on('sourcedata')` antes de `setPaintProperty`/`setData`) se reusará para selección terracota.

## Testing Decisions

- **Qué hace un buen test:** probar comportamiento externo visible (landmarks, URL, pins resaltados, sheet abierto, chat persistido, contraste AA) con datos mockeados en la costura del shell; no inspeccionar estado interno de MapLibre, clases Tailwind crudas ni paths de archivo; fijarse en razones citadas y atribución, no en prompt.
- **Módulos a testear (una sola costura alta pactada):** Shell integration (`nav` Radares con Radares mocked, `main` Mapa+lista 8 curadas, selección vía `?listingId` sincroniza hover/selected, `flyTo` invocado con reason, `aside` Chat por radar con reasoning/HITL) + e2e Playwright que lista `web-foundation.spec` ya cubre (axe, skip-link, reduced-motion). Unit mínimo solo para `scheduleSelectedFeaturePaint` con terracota y offset espiral heredado de playground.
- **Prior art:** `foundation.test.tsx` (semantic tokens), `geo-map-*.test.ts` (mock `Map` con `isStyleLoaded`/`setPaintProperty`/`once`/`on`), `chat-panel.test.tsx`/`message-list.test.tsx`/`use-chat-stream.test.ts` (stream+resume+decision), `brand-foundations.test.ts` + `logo-assets.test.ts` (tokens/brand), `web-foundation.spec.ts` (WCAG, skip, 320/768/1440, dark). Se extiende ese spec sin duplicar mocks de MapLibre.
- **Fuera de test en este incremento:** cluster, tiles reales, notifs proactivas, comparación multi; se dejan para suite siguiente.

## Out of Scope

- Comparador multi (selección múltiple, `compare` sheet/page) — deferred; solo single-select con `?listingId` y futura extensión a 3.
- Centro de notificaciones proactivo (fatiga, horario, duplicados, razón) — solo bell mock con badge y link a `/notifications` legacy.
- Panel filtros denso izquierda tipo REALL, score numérico (92%), terracota como error, Fraunces en body/tablas.
- Bottom-sheet draggable mobile, vector DB separada, Dagster/Prefect, microservicios, Kafka.
- Nueva paleta o rediseño de login; login mantiene flujo `magic-link` existente.
- Live OSM sin snapshot, inferencias presentadas como hechos, prompts/modelos sin versionar, ranking decidido por LLM, SQL libre desde agente.

## Further Notes

- **Referencias aplicadas:** `mapcn.dev` → sistema de pins y tokens desaturados; `fluidfunctionalism` → suavidad/blend sin neomorfismo pesado; `justfuckinguseshadcn` → densidad shadcn correcta; `elements.ai-sdk.dev` → blocks reasoning/HITL en chat. No replicar filtros densos, dark laptop forzado ni scores.
- **Brand hard constraints:** Zona protección ¼ ancho símbolo, terracota solo novedad, destructivo independiente, WCAG AA en nuevas combinaciones, sin casa literal/lupa/pin/robot/radar, símbolo reconocible 16px.
- **Atribución y licencia:** OSM ODbL via `GlobalAttribution` global + endpoint señales; mapa desaturado Luz serena no duplica control.
- **Migración:** `/radar` → `/` con sidebar, `/radar/new` → Dialog, `shortlist/dismissed` → filtros `?filter=` con alias legacy, `/radar/[id]/compare` → 404 controlado con mensaje hasta fase 2; todo preserva `check-web` (ESLint/TypeScript/Vitest/Playwright collection) y añade 0 violaciones axe serias.
- **Próximo plan:** comparativa + notifs con control de fatiga + bottom-sheet + vector tiles si hace falta lineage; spec separado.

