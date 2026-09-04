# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primario:** personas con poco tiempo que necesitan alquilar y mudarse pronto en Argentina. Mercado inicial CABA (alquiler residencial). Usan el producto en desktop y mobile mientras trabajan/estudian, con poca tolerancia al scroll compulsivo y a filtrar cientos de publicaciones repetidas.

**Job-to-be-done:** pasar de buscar manualmente en portales a tener un radar que entiende qué valoran, monitorea el mercado y les acerca una selección breve, explicada y accionable, conservando el control de la decisión final.

**Audiencias adicionales confirmadas:** no hay segmento secundario priorizado para V1. Futuro posible: compra, inversión o búsqueda para terceros, pero no define la V1 ni el shell inicial.

## Product Purpose

Umbral es un **radar personal de vivienda**: convierte intenciones cambiantes en búsquedas persistentes (radares), oportunidades explicables y aprendizaje controlado por la persona.

**Qué hace:** entiende qué busca cada persona (filtros duros + preferencias blandas), normaliza y enriquece listings, genera candidatos sin calcular todo el producto cartesiano, rankea con un scoring engine determinístico versionado y decide si notificar solo cuando algo merece atención, con razones claras.

**Por qué existe:** para devolver tiempo y tranquilidad, reducir ruido/repetición/trabajo manual y transformar una búsqueda agotadora en un acompañamiento personal, transparente y continuo.

**Qué significa éxito:** la persona entiende en una primera visita que Umbral sigue buscando por ella, distingue el radar persistente de un buscador convencional y describe la marca como cercana, clara y confiable; el sistema puede explicar por qué mostró (o no notificó) una oportunidad citando evidencia, snapshot de perfil y versión de scoring.

## Positioning

> Para personas que necesitan mudarse y no tienen tiempo para revisar cientos de publicaciones, Umbral es el copiloto de vivienda que aprende qué buscan, monitorea oportunidades y les acerca una selección explicada. A diferencia de los portales tradicionales, no obliga a empezar de cero cada vez ni confunde cantidad con relevancia.

**Mecanismo diferencial no copiable:** radar vivo por búsqueda (`SearchProfile`/`ProfileVersion` + `recommendation_runs`) que persiste intención, mantiene criterios versionados, aplica hard filters auditables + scoring determinístico puro y explica coincidencias/concesiones/incertidumbres; el chat es interfaz para refinar criterios, no la fuente de verdad (los listings viven como objetos persistentes en el radar, no solo en la conversación).

**Competencia de referencia contemplada:** portales de inventario (Mercado Libre, Zonaprop) y búsqueda con IA por lenguaje natural/colecciones/alertas (Roomix). Umbral no compite por “buscar mejor con IA”; compite por reducir la necesidad de buscar compulsivamente.

## Operating Context

**Unidad operativa:** `SearchProfile` (radar) por persona. Cada radar tiene criterios propios, listings propios, guardados/descartados propios, alertas y conversación contextual propia. V1 prioriza pocas oportunidades por pantalla, con jerarquía: qué apareció/dónde → por qué merece atención → coincidencias → concesiones/incertidumbres → precio/datos → acciones (ver/guardar/descartar/comparar/consultar).

**Flujo vivo:** crear radar en lenguaje natural → confirmar brief → revisar radar (nuevos matches, alta prioridad, bajaron de precio, guardados/descartados) → evaluar card → conversar sobre resultados (“compará estos tres”, “por qué me recomendaste este”) → aprender con control (propuesta HITL confirmable/deshacible).

**Entornos y canales V1:** web app (Next.js App Router, TypeScript, shadcn/ui, Tailwind, TanStack Query, MapLibre) + API Python/FastAPI. Alertas por inbox web y email; Telegram/WhatsApp/push en roadmap pero no V1. Beta cerrada por invitación y magic link; auth y email detrás de adapters.

**Datos y orquestación:** monolito modular + Postgres + PostGIS + pgvector + Redis (cache/queue) + object storage para snapshots crudos (retención acotada). Arquitectura medallion Bronze→Silver→Gold. Agent Orchestrator con LangGraph + checkpointer Postgres, structured outputs y tools internas explícitas; Scoring Engine puro, determinístico y versionado; RAG/embeddings solo recuperan contexto, no deciden ranking/notificación. Workers asincrónicos con scheduler simple al inicio; Dagster/Prefect solo si hace falta lineage/backfills. OpenTelemetry + Sentry.

**Ritual de tienda:** validación con 5-8 personas que buscan alquiler o se mudaron en los últimos 6 meses; pruebas de 5 segundos, asociación de atributos, comprensión de propuesta y comparación con portales. No preguntar solo “te gusta”.

## Capabilities and Constraints

**Capacidades confirmadas (V1):**
- Radares persistentes con filtros duros auditables y preferencias blandas versionadas (`SearchProfile`, `ProfileVersion`, `preference_facts`/`profile_criteria`, `concept_registry`).
- Ingesta → normalización → dedupe no destructivo con trazabilidad → geocoding (exact/block/neighborhood centroid/unknown) → enrichment por texto/metadata y señales urbanas OSM (contrato urbano versionado, snapshot inmutable con hash) → mercado (precio/m², variación) → embeddings/listings.
- Matching híbrido: LLM observa/interpreta y extrae observaciones; código determinístico filtra, puntúa (weighted sum × confidence + bonuses − penalties) y explica; `unknown` es valor de primera clase, no se inventa neutral.
- Candidate generation por etapas (hard filter → retrieval híbrido SQL/full-text/vector → fast/deep ranking → diversidad/fatiga) + fast path (<30s, flag `stale`) y slow path async.
- Recomendación y notificaciones con gate (threshold, frescura, unseen, novedad, budget de frecuencia, disponibilidad, confidence) y trazabilidad (perfil/scoring/snapshot usados).
- Chat contextual por radar con tools tipadas (`get_search_profile`, `update_search_profile`, `find_matches`, `explain_match`, `compare_listings`, `record_feedback` con `concept_feedback[]`, etc.); el agente no toca DB ni decide ranking solo.
- Mapa/lista/shortlist/comparador/detalle con evidencia y mapa; feedback explícito e implícito; learning HITL (0 auto-apply) con elevación soft→hard solo con confirmación.

**Restricciones y límites de promesa:**
- No promete vivienda perfecta, cobertura total ni comprensión mágica; no presenta inferencias como hechos ni oculta faltantes; terracota no es error (es acento de novedad); bosque es acción primaria.
- No usar embeddings como reemplazo de filtros duros; no ranking final por LLM generativo; no SQL libre desde el agente; no microservicios/Kafka/vector DB separada ni multi-agent complejo en V1.
- No inducción a relajar criterios sensibles para inflar resultados; lenguaje sin sesgos ni proxies de características protegidas; notificaciones con control de fatiga/horario/duplicados y razón auditable.
- Validación marcaria/dominios/redes de “Umbral” pendiente de verificación legal; este PRODUCT.md no autoriza uso comercial.

**Terminología canónica (ver `CONTEXT.md`):** Radar, Deseo expresado, Concepto, Vinculación de criterio, Hecho de preferencia, Preferencia suave vs Filtro duro, Observación, Criterio compilado, Hipótesis de preferencia, Modo de fuerza soft/hard y Elevación a hard, Trayectoria conversacional, Contrato urbano / Snapshot urbano / Señal urbana / Primitiva urbana / Atribución OSM, Catálogo de vivienda, Señales de entorno.

**Decisiones explícitamente diferidas:** session scoping real (hoy “esta vez” se modela como edición del radar con aclaración en la respuesta), pipeline de imágenes/visión, layout/space efficiency sin plano, días en mercado y precio vs comparables por barrio, trigger `price_drop` de notificaciones.

## Brand Commitments

**Nombre y descriptor:** Umbral. Descriptor inicial: `Copiloto para encontrar tu próximo lugar.` Puede perder protagonismo cuando la marca sea reconocida. El concepto `radar` nombra el mecanismo, no la marca.

**Ideas rectoras vinculantes:**
- Idea rectora (guía interna): `Tu próximo lugar puede encontrarte.`
- Línea principal: `Tu próximo lugar se acerca.`
- Idea de campaña: `Que tu próximo lugar te encuentre.`

**Plataforma de marca:** Propósito “devolver tiempo y tranquilidad”; Misión “entender, seguir el mercado y acercar selección breve con razones claras”; Visión “acompañamiento personal, transparente y continuo”; Promesa “se mantiene atento por vos y te avisa cuando algo merece tu atención”; Emoción principal alivio/calma (ilusión como acento, confianza como fundamento); Pilares: Menos búsqueda, Más afinidad, Razones claras, Siempre atento, Vos decidís. IA como medio, no centro del discurso.

**Personalidad y voz:** copiloto sereno con buen criterio. Rasgos: atento, claro, cercano (voseo rioplatense natural), sereno, proactivo, honesto, alegre con medida. Es/No es: cálido/no confianzudo, optimista/no ingenuo, proactivo/no insistente, inteligente/no grandilocuente, argentino/no caricaturesco, selectivo/no sentencioso, informal/no descuidado. Argentinidad por sintaxis/sensibilidad, sin “che” forzado ni lunfardo permanente.

**Principios de escritura y patrones de agente (vinculantes):** empezar por lo que importa, frases breves/conversacionales, explicar por qué cada propiedad fue seleccionada, mostrar incertidumbre sin jerga, recomendar acción conservando decisión, nunca declarar “perfecta/ideal/imperdible”, sin abuso de emojis/exclamaciones/referencias a IA, sin certeza no respaldada. Patrones de referencia: nueva selección, oportunidad destacada, incertidumbre, sin resultados, feedback (ver `docs/superpowers/specs/2026-08-26-umbral-brand-system-design.md:159-187`).

**Arquitectura verbal:** Tu radar, Oportunidades, Por qué encaja (coincidencias/concesiones/evidencia/faltantes), Guardados, Comparar, Ajustar el radar. Verbos preferidos: crear, ajustar, seguir, aparecer, acercar, entender, comparar, decidir. Evitar jerga tecnológica artificial (`Smart Match`, `AI Search`, `Umbral Assistant`); la voz del asistente es la voz de Umbral.

**Dirección visual “Luz serena” (compromiso aprobado conceptualmente, no arte final):** 
- Paleta: Bosque profundo `#293F38` (confianza/texto/acciones), Lino cálido `#F4EFE6` (fondo distintivo), Terracota `#DE6D4A` (novedad/acento), Arena `#D9C59F`, Marfil `#FFFAF2`. Escala neutral derivada de bosque + semánticos accesibles; WCAG AA obligatorio; terracota nunca es error.
- Tipografía: Fraunces Semibold solo para logotipo/titulares editoriales/hitos; DM Sans Regular/Medium/Semibold para interfaz/cuerpo/botones/datos/redes. Con fallbacks y estrategia de carga web.
- Logo “Umbral abierto”: arco/abertura simple con pequeño acento terracota de oportunidad; sin casa literal/lupa/pin/robot/radar genérico; debe funcionar en monocromo antes del acento y ser legible a 16 px; entregables: horizontal, símbolo, monocromo, positivo/negativo, app icon y favicon, con zona de protección y usos incorrectos. Boceto conceptual ≠ arte final vectorial.

**Principios de UI (marca en producto):** pocas oportunidades por pantalla, cada card explica por qué apareció, distinción visual/verbal coincide/no coincide/no sabemos, no reemplazar razones por score numérico, bosque para CTA primario/terracota para novedad, estados vacíos con calma y próximo paso, conversación como acompañamiento del radar, sin urgencia artificial ni FOMO, hacer visibles “ajustar criterios” y control de alertas.

**Assets existentes que vuelven compromiso:** suite vectorial en `apps/web/public/brand/` (horizontal color/dark/light, symbol color/dark/light, favicon con fondo lino), tokens en `apps/web/src/app/globals.css` y fuentes `next/font` en `apps/web/src/app/layout.tsx` (DM Sans `--font-sans`, Fraunces `--font-brand`). Todo ya alineado a Luz serena; tests en `apps/web/src/app/brand-foundations.test.ts`.

## Evidence on Hand

- **Brand system aprobado conceptualmente:** `docs/superpowers/specs/2026-08-26-umbral-brand-system-design.md` (11 capítulos, 2026-08-26, con criterios de aceptación e investigación recomendada).
- **Visión y arquitectura fundacional:** `vision-arquitectura-producto.md` (radar, scoring, medallion, modelo lógico).
- **SPEC de producto y sistema:** `SPEC.md` + nota de adaptación al repo (Apéndice A, NA-01 a NA-12).
- **Glosario de dominio:** `CONTEXT.md` (radar, concepto, observación, fuerza soft/hard, contrato urbano, etc.).
- **Assets de marca implementados:** `apps/web/public/brand/umbral-logo-horizontal-{color,dark,light}.svg`, `apps/web/public/brand/umbral-symbol-{color,dark,light}.svg`, `apps/web/public/brand/umbral-favicon.svg` (arco bosque + acento terracota; favicon sobre lino `#F4EFE6`).
- **Fundaciones visuales en código:** `apps/web/src/app/globals.css` (variables `--brand-*`, tokens `--background/--foreground/--card/--primary`, soporte `.dark`, `@theme inline`) y `apps/web/src/app/layout.tsx` (DM Sans + Fraunces vía `next/font/google`, `lang="es-AR"`, metadata `Tu próximo lugar se acerca.`).
- **Pimienta de verificación:** `apps/web/src/app/brand-foundations.test.ts` (palette + fonts), `apps/web/src/components/brand/brand-logo.tsx` y `apps/web/src/components/radar/map/map-luz-serena.tsx` / `map-style-luz-serena.json` (mapa en Luz serena).
- **Ausencias que no se deben fabricar:** testimonios, casos de éxito, métricas de conversión, benchmarks de scoring, precios/planes, clientes nombrados y claims legales de registro marcario. No existen en `docs/superpowers/specs/` ni en el codebase.

## Product Principles

1. **Menos búsqueda, más criterio.** Cada iteración debe reducir trabajo manual y ruido antes de agregar features. Si no baja scroll/fricción ni mejora la decisión, no entra.
2. **El radar decide, el chat traduce.** La fuente de verdad es el radar (criterios + observaciones + scoring versionado); el agente interpreta lenguaje, propone cambios y explica con evidencia, nunca inventa ni decide ranking solo.
3. **Razones antes que scores.** Toda oportunidad muestra coincidencias, concesiones e incertidumbres con evidencia y confianza; el número, si aparece, es secundario y no sustituye la explicación.
4. **Proactividad con permiso.** Notificar solo cuando hay novedad relevante y explicable, respetando umbrales, diversidad, fatiga, horario y duplicados; vos decidís siempre.
5. **Calma sistemática.** La marca y el producto reducen ansiedad: pocas opciones priorizadas, estados vacíos que guían, sin urgencia artificial, con WCAG AA y lenguaje honesto sobre lo que no se sabe.

## Accessibility & Inclusion

- **Estándar:** WCAG 2.1 AA en estados principales (texto, navegación y acciones sobre bosque `#293F38`, terracota `#DE6D4A` solo para novedad, no para error). Verificación de contraste antes de fijar tokens finales; foco visible (`:focus-visible` con `--ring`) y `skip-link` ya implementados en `globals.css`/`layout.tsx`. Respeto a `prefers-reduced-motion`.
- **Inclusión y lenguaje:** voseo rioplatense natural sin caricatura; evitar humor local forzado, lunfardo permanente o referencias a IA; no usar lenguaje discriminatorio ni proxies de características protegidas; comunicar faltantes e incertidumbre sin tecnicismos.
- **Cobertura:** toda combinación de paleta debe pasar AA; tipografía de interfaz en DM Sans (legible en tablas/filtros/comparaciones), Fraunces solo editorial; ningún estado crítico puede depender solo de color.
