---
name: Umbral
description: Copiloto para encontrar tu próximo lugar — Tu próximo lugar se acerca.
colors:
  brand-forest: "#293F38"
  brand-linen: "#F4EFE6"
  brand-terracotta: "#DE6D4A"
  brand-sand: "#D9C59F"
  brand-ivory: "#FFFAF2"
  background: "#F4EFE6"
  foreground: "#293F38"
  card: "#FFFAF2"
  muted: "color-mix(in srgb, #D9C59F 22%, #FFFAF2)"
  muted-foreground: "color-mix(in srgb, #293F38 68%, #F4EFE6)"
  border: "color-mix(in srgb, #D9C59F 55%, #FFFAF2)"
  input: "color-mix(in srgb, #D9C59F 65%, #F4EFE6)"
  ring: "color-mix(in srgb, #293F38 78%, #D9C59F)"
  accent: "color-mix(in srgb, #DE6D4A 18%, #FFFAF2)"
  destructive: "oklch(0.52 0.18 25)"
typography:
  display:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "clamp(2.25rem, 5vw, 3rem)"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Fraunces, Georgia, serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.01em"
  title:
    fontFamily: "DM Sans, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "DM Sans, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "DM Sans, Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.06em"
rounded:
  sm: "0.5rem"
  md: "0.625rem"
  lg: "0.75rem"
  xl: "1rem"
spacing:
  sm: "0.5rem"
  md: "1rem"
  lg: "1.5rem"
  xl: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.brand-forest}"
    textColor: "{colors.brand-ivory}"
    rounded: "{rounded.md}"
    padding: "8px 16px"
    height: "40px"
  button-primary-hover:
    backgroundColor: "color-mix(in srgb, #293F38 90%, black)"
    textColor: "{colors.brand-ivory}"
  button-muted:
    backgroundColor: "{colors.muted}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
    height: "32px"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.xl}"
    padding: "24px"
  input:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
    height: "40px"
---

# Design System: Umbral

## Overview

**Creative North Star: "Luz serena"**

Luz serena es una calidez editorial con claridad digital. La luz que se cuela por el umbral — el arco — organiza todo: el fondo lino respira, el bosque sostiene, y un punto terracota aparece solo cuando hay una oportunidad que merece atención. Es adulta y luminosa sin volverse fría (nada de startup de IA) ni caricaturesca (nada de inmobiliaria tradicional con llaves en primer plano).

El sistema es sereno y nítido por defecto: pocas oportunidades por pantalla, ritmo tranquilo, nada de urgencia artificial. La densidad es baja en marketing y media-baja en producto; el chat acompaña al radar, no lo reemplaza. El mapa y la lista son la fuente de verdad, el chat traduce intención en criterios con voseo rioplatense natural y sin lunfardo forzado.

No es maximalista, no es brutalista y no es futurista. Rechaza casa literal, lupa, pin, robot y radar genérico en el símbolo — el arco basta — y rechaza escaneos futuristas permanentes; el pulso del radar es suave y deliberado.

**Key Characteristics:**
- Luminosa pero contenida: lino/ivory como campo, bosque como estructura
- Selectiva, no sentenciosa: explica coincidencias, concesiones y no sabemos en cada card
- Tonal antes que sombría: profundidad por color y borde, no por sombra dura
- Serenamente interactiva: transiciones cortas (120–200ms), foco visible siempre

## Colors

Paleta cálida de cinco bases con escala neutral derivada del bosque y semánticos accesibles; terracota nunca es error, es novedad.

### Primary
- **Bosque profundo** (#293F38): confianza, texto principal, navegación y acción primaria (bg-primary, text-foreground). Se usa en botones primarios, pins por defecto del mapa y títulos.
- **Terracota** (#DE6D4A): acento de oportunidad — el punto que aparece — y novedad puntual. Nunca para destructivo ni para estados de error. En mapa: pin seleccionado (circle-color terracota) y foco en floating list.

### Secondary
- **Arena** (#D9C59F): fondo secundario, recursos gráficos y tramas sutiles. Base para generar muted, border e input vía color-mix con marfil/lino. En el mapa: urban-points circulares con 55–65% de arena sobre marfil.

### Neutral
- **Lino cálido** (#F4EFE6): fondo distintivo de pagina (background) y calma general; también background del mapa (background-color #F4EFE6) y del favicon.
- **Marfil** (#FFFAF2): superficie elevada — cards, popovers, sheet de detalle — alternativa al blanco puro.
- **Muted** (color-mix arena 22% + marfil): fondos suaves para skeletons, tabs no seleccionados y botones muted (bg-muted).
- **Muted foreground** (color-mix bosque 68% + lino): texto secundario y descripciones (text-muted-foreground).
- **Border** (color-mix arena 55% + marfil): separadores y bordes de card (border-border).
- **Input** (color-mix arena 65% + lino): borde de campos y del composer textarea (border-input).
- **Ring** (color-mix bosque 78% + arena): anillo de foco visible (focus-visible:ring-ring, 2px).
- **Destructive** (oklch 0.52 0.18 25; dark 0.7 0.14 25): solo para error real (aria-invalid, FieldError text-destructive).

### Named Rules
**The Terracota Is Opportunity Rule.** Terracota aparece en ≤8% de cualquier pantalla — pin seleccionado, dot de pulso, badge de novedad. Si compite con bosque, pierde; la rareza es su valor. No usar para error, warning ni CTA primario.
**The Linen Field Rule.** Toda pagina y todo mapa descansan sobre lino (#F4EFE6). Marfil solo eleva. Nunca invertir el campo a blanco puro en light mode.

## Typography

**Display Font:** Fraunces Semibold (con Georgia, serif)
**Body Font:** DM Sans Regular/Medium/Semibold (con Arial, Helvetica, sans-serif)
**Label/Mono Font:** DM Sans (no mono distinto en V1)

**Character:** Fraunces casi no habla en producto — solo logotipo, titulares de bienvenida o hitos breves — y cuando lo hace es Semibold con tracking negativo suave. DM Sans sostiene todo lo demás: interfaz, datos, botones y redes, con ritmo conversacional y voseo. La pareja es editorial sin ser pretenciosa, adulta sin ser fría.

### Hierarchy
- **Display** (Fraunces, 600, clamp 2.25rem–3rem / 36–48px, 1.1, -0.02em): titulares de marketing y nombre de marca. En código: logo SVG 46px/-1.4 y page h1 text-4xl→5xl tracking-tight. Uso escaso y nunca en tablas/filtros/comparaciones densas.
- **Headline** (Fraunces, 600, 1.125rem / 18px, 1.2, -0.01em): CardTitle y títulos de sheet. Reserva editorial dentro del producto.
- **Title** (DM Sans, 600, 0.875rem / 14px, 1.4): encabezados de sección “Por qué encaja”, “Concesiones”, “Señales urbanas”; también FloatingList “oportunidades”.
- **Body** (DM Sans, 400, 0.875rem / 14px, 1.6): párrafos, descripciones, CardDescription, mini-card y composer textarea. Longitud óptima 65–75ch en detalle/lista; muted-foreground para secundario.
- **Label** (DM Sans, 500, 0.75rem / 12px, 1.4, 0.06em, uppercase opcional): etiquetas de campo, tabs Todos/Guardadas/Descartadas, breadcrumbs y texto técnico del mapa. Tracking 0.18em en overline “Fundación del runtime”.

### Named Rules
**The Fraunces Rarely Rule.** Fraunces es para el momento editorial, no para el dato. UI densa (filtros, tablas, comparador) siempre en DM Sans.
**The One Weight Up Rule.** La jerarquía se construye subiendo un peso (400→500→600), no agrandando todo. Evitar exclamaciones y emojis; la voz ya es cercana por sintaxis.

## Layout

Modelo de pagina limpia con contención y respiración: max-w-3xl para estados vacíos/marketing (`mx-auto px-6 sm:px-10 py-16`), y full-bleed con paneles superpuestos para el shell del radar (`flex h-[calc(100vh)] bg-background` con mapa flex-1 + sidebar 280px / 64px colapsado + chat 400px + floating list 320px y detail sheet 380px). El chat no domina el viewport; acompaña a mapa/lista.

Grid: Tailwind v4 sin tailwind.config — escala 4px nativa; contenedores usan flex y gap-2/gap-3/p-2/p-3/p-4/p-6. Ritmo de 8px: spacing sm 8px (0.5rem) para separadores finos, md 16px para gaps y padding de card interno (p-6), lg 24px y xl 32px para secciones. Border y tono separan antes que espaciado extra. Responsive: mapa ocupa todo entre 768–1280 con floating list absoluta `left-3 top-3 bottom-3 w-[320px] max-[1024px]:hidden` y sheet derecha `max-[1280px]:hidden`; en mobile el radar resuelve con tabs Mapa/Lista/Chat. skipped-link fijo `left-4 top-3` y `min-width:20rem (320px)` como ancho mínimo soportado.

## Elevation & Depth

Plana por defecto con capas tonales; la sombra es cortesía, no lenguaje. La profundidad se comunica por contraste lino↔marfil (background vs card), por borde sutil (border-border 55% arena) y por z-index de paneles superpuestos. Las sombras solo aparecen para separar superficies flotantes del mapa y para feedback de estado.

### Shadow Vocabulary
- **shadow-xs** (`0 1px 2px rgba(0,0,0,0.05)`): botones primarios y composer textarea en reposo — casi imperceptible.
- **shadow-sm** (`0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06)`): cards estándar (Card `shadow-sm`) y mini-cards del chat.
- **shadow / shadow-lg** (`0 8px 24px rgba(41,63,56,0.12)`): sheets y floating list sobre mapa; la única sombra que se siente como elevación.

### Named Rules
**The Flat-By-Default Rule.** Superficies planas en reposo; la sombra aparece solo en hover, selección o overlay. Si una card ya se distingue por tono y borde, no añadir sombra extra.

## Shapes

Lenguaje de forma suave y arquitectónico: esquinas redondeadas contenidas que evocan arco/abertura sin literalidad, coherente con el símbolo de arco bosque + acento terracota.

- **Radius:** sm 8px (0.5rem) para chips/pills del chat (rounded-full 9999 para sugerencias), md 10px (0.625rem) para botones e inputs (rounded-md), lg 12px (0.75rem) para alerts y composer, xl 16px (1rem) para cards elevadas y floating list (Card rounded-xl). Derivado de --radius 12px con offsets -4/-2/+4.
- **Bordes:** 1px sólido en border-color derivado de arena/marfil; inputs con border-input, cards con border-border. Nunca borde grueso ni doble borde.
- **Clipping:** sin recortes diagonales ni blobs; el rectángulo con esquinas suaves basta. El mapa usa rect sin radius al ras del viewport; los paneles flotantes sí llevan xl.
- **Geometría recurrente:** arco de 6px stroke en logo/símbolo, pulsos circulares en mapa (pins 7px→10px seleccionado, stroke marfil 1.5–2px).

## Components

### Buttons
Serenos y nítidos: bosque sólido, tipografía DM Sans contenida, sin grandilocuencia.

- **Shape:** suavemente redondeado (10px / rounded-md), gap 8px si lleva icono
- **Primary:** bosque (#293F38) sobre marfil, 40px altura (min-h-10), padding 8px 16px (px-4 py-2), text-sm 14px medium, shadow-xs, transición 150ms
- **Hover / Focus:** hover bosque al 90% (bg-primary/90), focus anillo 2px ring (color-mix bosque 78% arena) con offset 2px background (focus-visible:ring-2 + ring-offset)
- **Secondary / Muted:** fondo muted (color-mix arena 22% marfil) texto bosque, 32px (h-8) padding 8px 12px, hover muted/80; usado para Rechazar/Descartar/Guardar y tabs no seleccionados
- **Disabled:** pointer-events none + opacity 50
- **Composer Send:** primary + disabled cuando `value.trim()===""` o streaming en curso

### Chips
- **Style:** sugerencias del chat y razones de feedback como pills redondeadas (rounded-full, bg-background, px-3 py-1 text-xs) con shadow-xs y border sutil; tabs de floating list usan variant muted vs bosque sólido seleccionado
- **State:** seleccionado = bosque sobre marfil; no seleccionado = muted sobre bosque; feedback reasons en mini-card usan border-input sobre background para lista envolvente

### Cards / Containers
- **Corner Style:** xl 16px (rounded-xl) para tarjetas principales; lg 12px para alerts y estados vacíos
- **Background:** marfil (#FFFAF2 / bg-card) sobre lino
- **Shadow Strategy:** shadow-sm en reposo; shadow-lg solo en sheet/floating sobre mapa
- **Border:** 1px solid border (arena 55% marfil); en propuesta destacada border-border/60; hover eleva a ring si es clickeable
- **Internal Padding:** p-6 (24px) con header gap 1.5 y content pt-0; en floating list p-2/p-3 compacto para densidad de lista

### Inputs / Fields
- **Style:** 40px altura, w-full, rounded-md (10px), border-input, bg-background, px-3 py-2 text-sm, placeholder muted-foreground
- **Focus:** ring-2 ring + ring-offset-2 background, sin outline nativo; transición rápida, respeta prefers-reduced-motion
- **Error / Disabled:** aria-invalid:border-destructive, FieldError text-sm text-destructive; disabled cursor-not-allowed opacity-50
- **Textarea composer:** min-h-10, resize-y, rows 2, placeholder “Escribile a Umbral…”, desactivada durante streaming (sending/running/resuming/waiting_decision)

### Navigation
- **Style:** sidebar 280px expandida / 64px colapsada, bg-card, border-r border-border; header h-14 border-b con BrandLogo (horizontal dark h-6 vs symbol h-7)
- **Typography:** ítem 14px, hover bg-muted, seleccionado bg-muted font-medium, aria-current page
- **Default/Hover/Active:** hover muted, active/selected muted persistente con texto bosque
- **Mobile:** tabs inferiores Mapa/Lista/Chat (flex justify-around border-t, text-sm medium vs muted-foreground) y composer con gap-2

### Proposal Card
Componente firma del sistema: confirma el radar como fuente de verdad. Card con border-border/60 p-3, título xs medium (“Preferencia propuesta”), lista de campos xs muted-foreground con strong foreground, y acciones Aprobar (foreground sobre background) / Rechazar / Editar en h-8 px-3 text-xs. Entrada para editar presupuesto con input number + botón Aplicar edición.

### Map Luz Serena
Signature component. Fondo lino #F4EFE6, raster OSM 82–92% opacidad, pins bosque #293F38 7px con stroke marfil 1.5px; seleccionado terracota #DE6D4A 10px stroke 2px; hover 9px. Agrupado con offset para evitar solapamiento. Controles NavigationControl sin brújula top-right. Estado vacío centrado con texto muted-foreground sobre lino.

## Do's and Don'ts

### Do:
- **Do** usar bosque para acciones primarias y terracota solo para novedad seleccionada — la rareza es la señal.
- **Do** mantener lino como campo y marfil para elevar; el tono separa antes que la sombra.
- **Do** reservar Fraunces para momentos editoriales (logo, bienvenida, hito) y sostener toda la UI densa en DM Sans.
- **Do** distinguir visual y verbalmente coincide / no coincide / no sabemos en cada oportunidad (ver OpportunityDetailSheet: “Por qué encaja” + “Concesiones” + Alert “Incertidumbres”).
- **Do** usar un solo ring de foco (2px color-mix bosque/arena) y skip-link visible; respetar prefers-reduced-motion.
- **Do** repetir OSM attribution globalmente (`— OpenStreetMap contributors`) y en provisión de señales urbanas.

### Don't:
- **Don't** usar terracota para error, warning o fondos grandes — pertenece a la oportunidad que aparece.
- **Don't** convertir Fraunces en fuente de interfaz ni en tablas/filtros/comparaciones.
- **Don't** transformar el chat en catálogo: los listings viven en el radar/mapa como objetos persistentes, no solo como burbujas.
- **Don't** inventar casa literal, lupa, pin, robot o radar genérico en el símbolo; el arco abierto ya es Umbral.
- **Don't** crear urgencia artificial, contadores falsos ni FOMO; los estados vacíos ofrecen calma y un próximo paso (“Probá ajustar el radar en el chat”).
- **Don't** declarar una propiedad “perfecta/ideal/imperdible”; explicar razones con evidencia y confianza.
- **Don't** añadir sombra dura a cards que ya se separan por tono y borde; flat-by-default.
