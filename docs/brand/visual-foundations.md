# Fundaciones visuales — Umbral (Luz serena)

Fecha: 2026-08-26
Principio de logo: Umbral abierto
Geometría aprobada: `balanced` — arco circular `M14 52V30C14 18.954 22.954 10 34 10s20 8.954 20 20v22` + acento `M29 52h10`.

Este documento es el contrato operativo para usar color, tipografía y logo sin rediseñar pantallas de producto.

## 1. Inventario de assets

Todos los archivos viven bajo `apps/web/public/brand` y se sirven como URLs estáticas `/brand/*`.

| Archivo | Uso | Tamaño base |
| --- | --- | --- |
| `umbral-symbol-color.svg` | Símbolo a color (bosque + terracota) para fondos claros lino/marfil. | `64×64` |
| `umbral-symbol-dark.svg` | Símbolo mono bosque `#293F38` para fondos claros cuando se requiere un solo color. | `64×64` |
| `umbral-symbol-light.svg` | Símbolo mono marfil `#FFFAF2` para fondos oscuros o bosque `#293F38`. | `64×64` |
| `umbral-logo-horizontal-color.svg` | Lockup horizontal a color (símbolo color + palabra bosque) para fondos claros. | `280×64` |
| `umbral-logo-horizontal-dark.svg` | Lockup mono bosque para fondos claros con impresión a un color. | `280×64` |
| `umbral-logo-horizontal-light.svg` | Lockup mono marfil para fondos oscuros. | `280×64` |
| `umbral-favicon.svg` | Favicon: mismo símbolo a color sobre campo lino redondeado con margen ≥6 unidades. | `64×64` |

### Regla de variante por fondo

- **Lino `#F4EFE6` o marfil `#FFFAF2`:** `*-color.svg` por defecto; `*-dark.svg` si la salida es mono.
- **Bosque `#293F38`:** `*-light.svg` exclusivamente; nunca usar `*-color.svg` o `*-dark.svg` sobre bosque (contraste insuficiente).
- **Fotografía:** usar `*-light.svg` con un scrim oscuro o `*-color.svg` dentro de un contenedor marfil/lino. Nunca colocar el logo directamente sobre área ocupada y de alto contraste sin respaldo.

Todos los SVG incluyen `xmlns`, `viewBox`, `role="img"`, `aria-labelledby`, `<title>Logo de Umbral</title>` y `<desc>` en español, sin `<filter>` ni `<image>`.

## 2. Zona de protección y tamaños mínimos

- **Zona de protección:** espacio libre igual a **un cuarto del ancho del símbolo** en los cuatro lados. Para el símbolo de `64` unidades, `16` unidades de respiración; para el horizontal de `280×64`, `16` unidades equivalentes (el espacio ya está contemplado entre símbolo y palabra).
- **Mínimos:**
  - Símbolo: **16 px** (favicon y compact UI).
  - Horizontal digital: **100 px** de ancho.
  - Horizontal impreso: **25 mm** de ancho.
- No recortar ni añadir elementos dentro de la zona de protección.

## 3. Color

### Valores fuente (única fuente de verdad en `globals.css`)

| Token | Hex | Rol |
| --- | --- | --- |
| `--brand-forest` | `#293F38` | Confianza, texto principal, acciones primarias, bosque. |
| `--brand-linen` | `#F4EFE6` | Fondo distintivo y calma. |
| `--brand-terracotta` | `#DE6D4A` | Oportunidad/novedad, acento puntual. No es error. |
| `--brand-sand` | `#D9C59F` | Fondos secundarios y recursos gráficos. |
| `--brand-ivory` | `#FFFAF2` | Superficies elevadas, alternativa a blanco. |

### Mapeo semántico (shadcn)

Los componentes consumen solo tokens semánticos (`bg-primary`, `text-muted-foreground`, etc.). Los tokens semánticos se derivan de los valores fuente:

**Light (`:root`):**
```
--background: var(--brand-linen)
--foreground: var(--brand-forest)
--card: var(--brand-ivory)
--card-foreground: var(--brand-forest)
--popover: var(--brand-ivory)
--popover-foreground: var(--brand-forest)
--primary: var(--brand-forest)
--primary-foreground: var(--brand-ivory)
--secondary: color-mix(in srgb, var(--brand-sand) 42%, var(--brand-ivory))
--secondary-foreground: var(--brand-forest)
--muted: color-mix(in srgb, var(--brand-sand) 22%, var(--brand-ivory))
--muted-foreground: color-mix(in srgb, var(--brand-forest) 68%, var(--brand-linen))
--accent: color-mix(in srgb, var(--brand-terracotta) 18%, var(--brand-ivory))
--accent-foreground: var(--brand-forest)
--border: color-mix(in srgb, var(--brand-sand) 55%, var(--brand-ivory))
--input: color-mix(in srgb, var(--brand-sand) 65%, var(--brand-linen))
--ring: color-mix(in srgb, var(--brand-forest) 78%, var(--brand-sand))
--destructive: oklch(0.52 0.18 25)  // independiente de terracota
```

**Dark (`.dark`):**
```
--background: color-mix(in srgb, var(--brand-forest) 94%, black)
--foreground: var(--brand-ivory)
--card: color-mix(in srgb, var(--brand-forest) 90%, var(--brand-ivory))
--primary: var(--brand-ivory)
--primary-foreground: var(--brand-forest)
--destructive: oklch(0.7 0.14 25)
... // ver globals.css para el resto, siempre derivado de brand con color-mix
```

**Exposición a Tailwind:** en `@theme inline` se exponen `--font-sans: var(--font-sans)` y `--font-brand: var(--font-brand)` y todos los colores semánticos.

**Reglas WCAG 2.2 AA:** cada combinación texto/fondo introducida por este incremento debe cumplir AA. Terracota no sustituye a `--destructive`.

## 4. Tipografía

- **Display / marca:** `Fraunces Semibold` (`--font-brand`) — solo para logotipo, titulares de marketing y momentos editoriales breves. No usar en tablas, filtros, comparaciones o explicaciones densas.
- **Interfaz / cuerpo:** `DM Sans Regular/Medium/Semibold` (`--font-sans`) — UI, cuerpo, botones, datos y redes.
- **Carga:** `next/font/google` en `apps/web/src/app/layout.tsx` a nivel módulo:

```ts
import { DM_Sans, Fraunces } from "next/font/google";

const dmSans = DM_Sans({ subsets: ["latin"], display: "swap", variable: "--font-sans" });
const fraunces = Fraunces({ subsets: ["latin"], display: "swap", variable: "--font-brand" });

// en <html>
<html lang="es-AR" className={`${dmSans.variable} ${fraunces.variable}`}>
```

- **Aplicación:** `body { font-family: var(--font-sans), Arial, Helvetica, sans-serif; }`. Fraunces solo vía clase `font-brand` o elemento `<text>` del lockup SVG (`font-family="Fraunces, Georgia, serif"`).

## 5. Usos prohibidos

- Distorsionar, rotar, sesgar o cambiar proporciones del símbolo o palabra.
- Añadir sombras, contornos, degradados o filtros.
- Recolorar fuera de las tres variantes aprobadas (color / dark / light).
- Colocar sobre fondos ocupados sin respaldo ni contraste.
- Convertir el arco en casa literal, lupa, pin, robot o radar genérico.
- Usar terracota como color de error, destrucción o advertencia.
- Aplicar Fraunces a cuerpo largo, UI densa o datos tabulares.

## 6. Uso del componente `BrandLogo`

Componente server-compatible sin directiva `use client`, basado en `next/image` con lookup estático. No acepta rutas arbitrarias ni SVG inline.

```tsx
import { BrandLogo } from "@/components/brand/brand-logo";

// Horizontal a color (default) — cabeceras claras
<BrandLogo />

// Equivalente explícito
<BrandLogo layout="horizontal" tone="color" />

// Horizontal mono bosque — impresión o fondo claro mono
<BrandLogo layout="horizontal" tone="dark" />

// Horizontal mono marfil — header bosque o hero oscuro
<BrandLogo layout="horizontal" tone="light" />

// Símbolo a color — favicon, avatar, marcador de mapa claro
<BrandLogo layout="symbol" tone="color" />

// Símbolo mono bosque — fondos lino/marfil mono
<BrandLogo layout="symbol" tone="dark" />

// Símbolo mono marfil — superficies oscuras, navegación bosque, mapa nocturno
<BrandLogo layout="symbol" tone="light" />

// Con clase y prioridad opcional (above-the-fold)
<BrandLogo className="h-8 w-auto" priority />
```

Props: `layout?: "horizontal" | "symbol"` (default `horizontal`), `tone?: "color" | "dark" | "light"` (default `color`), `className?: string`, `priority?: boolean`. Dimensiones internas: `280×64` horizontal, `64×64` símbolo; `alt="Umbral"`.

Metadata ya apunta al favicon:

```ts
export const metadata: Metadata = {
  title: "Umbral",
  description: "Tu próximo lugar se acerca.",
  icons: { icon: "/brand/umbral-favicon.svg" },
};
```

## 7. Export a PNG (cuando sea necesario)

Los SVG son la fuente; el PNG se genera localmente bajo demanda. Detectado en esta máquina: **ni Inkscape ni ImageMagick (`magick`) están disponibles**. `C:\WINDOWS\system32\convert.exe` corresponde a la utilidad de conversión de sistema de archivos NTFS, no a ImageMagick.

### Comandos de exportación cuando la herramienta exista

**Inkscape (recomendado):**
```powershell
inkscape apps\web\public\brand\umbral-symbol-color.svg --export-type=png --export-filename=umbral-symbol-color-512.png -w 512 -h 512
inkscape apps\web\public\brand\umbral-logo-horizontal-color.svg --export-type=png --export-filename=umbral-logo-horizontal-color-560.png -w 560 -h 128
inkscape apps\web\public\brand\umbral-favicon.svg --export-type=png --export-filename=umbral-favicon-512.png -w 512 -h 512
```

**ImageMagick:**
```powershell
magick -background none -density 600 apps\web\public\brand\umbral-symbol-color.svg -resize 512x512 umbral-symbol-color-512.png
magick -background none -density 600 apps\web\public\brand\umbral-logo-horizontal-color.svg -resize 560x128 umbral-logo-horizontal-color-560.png
```

No se añade dependencia de exportación al repo; instalar localmente la herramienta que corresponda.

## 8. Verificación

Ver `docs/brand/logo/concepts/README.md` para los tres conceptos y el registro de la geometría aprobada (`balanced` 2026-08-26). La suite de producción verifica con:

```powershell
npm --workspace @umbral/web run test -- src/components/brand/logo-assets.test.ts
npm --workspace @umbral/web run test -- src/app/brand-foundations.test.ts src/components/ui/foundation.test.tsx
npm --workspace @umbral/web run test -- src/components/brand/brand-logo.test.tsx
npm --workspace @umbral/web run test -- src/app/page.test.tsx
```

y la inspección manual a 320/768/1440 px en light/dark sin regresiones de contraste ni de carga de fuentes.

## 9. Próximos pasos (fuera de este incremento)

No rediseñar pantallas de producto, chat, cards, navegación o marketing en este incremento. La aplicación a componentes críticos de UI corresponde al siguiente plan.
