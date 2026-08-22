# Playground Real Snapshot

## Goal

Permitir que el Geo Lab inspeccione listings reales y su contexto urbano real a
partir de un snapshot JSON local, sin conectar la aplicación web al runtime
productivo ni permitir mutaciones sobre Postgres.

## Scope

- El snapshot se genera con un comando read-only contra Postgres/PostGIS.
- El archivo contiene listings normalizados y, por listing, features GeoJSON y
  buckets de distancias para recalcular primitivas y señales con el contrato
  urbano existente.
- El launcher recibe un path opcional y descubre por defecto
  `.data/playground/real-snapshot.json`.
- Geo Lab muestra la fuente demo y el snapshot como fuentes seleccionables.
- Conversation Lab conserva el fixture demo y su estado en memoria.
- Si el snapshot no existe, el playground sigue funcionando en modo demo.

## Non-goals

- No consultar la base de datos desde el API liviano en cada interacción.
- No escribir perfiles, listings, señales, snapshots ni eventos.
- No exportar descripciones completas, media ni credenciales por defecto.
- No agregar una segunda implementación de scoring urbano.
- No convertir el snapshot en un artifact versionado del repositorio.

## Snapshot contract

```json
{
  "id": "real-snapshot-<urban_snapshot_uuid>",
  "profile": {
    "id": "<deterministic uuid>",
    "name": "Real snapshot",
    "operation": "rental",
    "zones": [],
    "status": "active",
    "version": 1
  },
  "listings": [
    {
      "id": "<listing uuid>",
      "uuid": "<listing uuid>",
      "source_id": "...",
      "external_id": "...",
      "url": "...",
      "neighborhood": "...",
      "latitude": -34.5,
      "longitude": -58.4,
      "geo_precision": "exact",
      "total_cost": 1000,
      "price_value": 900,
      "price_currency": "USD",
      "expenses_value": null,
      "surface_m2": 50,
      "rooms": 2,
      "bedrooms": 1,
      "floor": 3,
      "property_type": "apartment",
      "amenities": []
    }
  ],
  "urban": {
    "snapshot_id": "<urban snapshot uuid>",
    "contract_version": "urban-contract-v2",
    "by_listing": {
      "<listing uuid>": {
        "snapshot_id": "<urban snapshot uuid>",
        "features": [],
        "poi_distances": {},
        "linear_distances": {}
      }
    }
  }
}
```

The `features` list contains only id, name, category, kind, distance and
GeoJSON geometry. Distance buckets use the existing calculator input shape:
`count_300m`, `count_600m` and `nearest_m` each contain source distances, so
the inspector can preserve missing-versus-zero semantics and recompute the
published formulas.

## Safety and failure behavior

- The exporter opens a SQLAlchemy session and performs only SELECTs.
- Listings without usable coordinates are excluded and reported in the CLI
  summary.
- A missing snapshot path is not an error for the launcher; it produces a
  demo-only catalog and a visible source label.
- Invalid snapshot JSON or an unknown listing returns the existing playground
  problem response rather than falling back silently.
- Snapshot data is read-only and all conversation profile changes remain in the
  existing in-memory adapter.
