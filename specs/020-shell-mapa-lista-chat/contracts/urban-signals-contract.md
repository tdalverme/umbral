# Urban Signals — contrato y snapshot para el shell

- **Contrato:** versión usada por playground (`urban-contract v2` si existe, si no `v1`), categorías `transporte`, `café`, `parque` + nuevas `escolar`, `deportivo`, `cultural`, `bici`, `salud` (al menos transporte real, resto mock gris fallback)
- **Primitivas:** `count_300m`, `count_600m`, `distance_nearest` por categoría y listing
- **Snapshot:** importado Bronze→Silver, inmutable, con `source: OSM`, `date`, `sha256`; lectura via `GET /urban/signals`
- **Regla unknown:** si no hay dato, `value=unknown`, UI muestra "no sabemos — punto para consultar" + evidencia faltante, no filtra ranking
- **Atribución:** requisito ODbL cubierto por `GlobalAttribution` global + `source` en payload; no se añade `maplibre` attributionControl
