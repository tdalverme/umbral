# Conceptos — Umbral abierto

Tres refinamientos del símbolo “Umbral abierto” con acento terracotta. Todos usan `viewBox="0 0 64 64"`, sin filtros, degradados ni fuentes embebidas.

## Criterios de comparación

Evaluar cada concepto con las mismas cinco verificaciones:

1. Recognition at 16 px and 24 px.
2. Clear opening/transition metaphor without reading as a house.
3. Stable silhouette in one color.
4. Optical balance beside the word “umbral”.
5. No collision or disappearance on linen, ivory, and forest backgrounds.

## Archivos

| Concepto | Archivo | Geometría clave |
| --- | --- | --- |
| balanced | `umbral-open-balanced.svg` | Arco circular con base recta (`M14 52V30C14 18.954 22.954 10 34 10s20 8.954 20 20v22`) y acento `M29 52h10`. |
| soft | `umbral-open-soft.svg` | Arco ancho y bajo (`M10 52V34c0-13.255 10.745-24 24-24s24 10.745 24 24v18`) y acento `M29 52h10`. |
| threshold | `umbral-open-threshold.svg` | Mismo arco que `balanced` más línea de suelo `M8 52h18m16 0h16` y acento `M29 52h10`. |

## Verificación de reducción

Abrir cada SVG a 16, 24, 64 y 192 px sobre fondos lino `#F4EFE6`, marfil `#FFFAF2` y bosque `#293F38`, más una variante monocromo. Confirmar que el acento terracota `#DE6D4A` no desaparece ni colisiona.

## Validación técnica

```powershell
Get-ChildItem docs\brand\logo\concepts\*.svg | ForEach-Object { [xml](Get-Content -Raw $_.FullName) | Out-Null }
```

Debe salir con código 0 y sin errores de parser.

## Selected geometry

`balanced` was approved on 2026-08-26. All production variants derive from this geometry; the other files remain concept records and are not shipped by the web app.
