# ADR 0001: Proveedor de modelo del agente conversacional

**Status**: Aceptado
**Date**: 2026-08-10
**Owner**: team-agent
**Version**: 1.0.0
**Spec**: H4.4 (UM-H4-026..UM-H4-030), diferido asignado a H4.4 en las notas de
aceptacion de H4.1/H4.2/H4.3 (clarificacion Q1).

## Context

El graph conversacional (H4.1..H4.4) consume un modelo generativo para dos
salidas estructuradas: compilacion de intencion (intent-schema-v3) y redaccion
de respuestas grounded (reply-schema-v3). La eleccion del proveedor define
costo, calidad, latencia, privacidad y operabilidad de la beta, y condiciona
la tabla de precios (`price-table-v1`) y los presupuestos (`AGENT_BUDGET_*`).

## Decision drivers

- **Costo por caso**: el evalu del dataset golden mide costo por caso; el
  presupuesto por usuario/sesion lo acota (FR-005, FR-012..FR-016).
- **Calidad estructurada**: las dos salidas son JSON validado; el proveedor
  debe cumplir el schema de forma consistente (FR-005).
- **Latencia percibida**: primer fragmento del chat dentro de
  `AGENT_MODEL_TIMEOUT_SECONDS` + budget de tools (H4.3).
- **Privacidad**: los mensajes contienen contenido de conversacion del
  usuario; el proveedor debe aceptar el tratamiento y retencion acordados y
  0 PII en telemetria.
- **Operabilidad**: timeouts, retries acotados, manejo de errores tipados y
  un flujo de evals real acotado por presupuesto de eval (Q4).

## Alternatives considered

| Alternativa | Costo/1k in+out | Calidad estructural | Latencia | Privacidad | Operabilidad |
| --- | --- | --- | --- | --- | --- |
| Proveedor A (endpoint gestionado propio) | media | alta (salidas validadas) | media | alta (endpoint propio, retencion controlada) | alta (gateway `ManagedModelGateway` ya existe) |
| Proveedor B (API publica generica) | baja | media (requiere validacion y reintentos) | alta | media (datos a terceros) | media |
| Modelo local/embeddings-only | muy baja | baja para generacion | muy alta | muy alta | baja para el volumen de beta |

El endpoint gestionado propio (A) ya esta soportado por
`ManagedModelGateway` (H4.1) con retry acotado, clasificacion de errores y
uso de tokens, y es el unico que permite el tratamiento de datos controlado
que la beta exige.

## Decision

Adoptar el **endpoint gestionado propio** (opcion A) como proveedor de modelo
del agente conversacional.

- `AGENT_MODEL_PROVIDER=managed` en entornos no locales; `fake` sigue siendo
  el default local (adapter determinista para tests y harness, Q4).
- `AGENT_MANAGED_ENDPOINT`/`AGENT_MANAGED_API_KEY` configuran el endpoint.
- Los evals con el proveedor real corren en `scripts/run-real-evals.ps1`
  (flujo opt-in, presupuesto de eval acotado, fuera de CI).
- La tabla de precios (`price-table-v1`) se alinea con el precio del modelo
  gestionado elegido.

## Consequences

- El costo por caso queda acotado por los presupuestos y es predecible via
  `price-table-v1`.
- La eleccion de un modelo concreto dentro del endpoint gestionado es un
  parametro de release (`graph-releases-v1`), evaluable y revertible sin
  mutar runs previos (Q6).
- Riesgo de latencia del endpoint gestionado: monitoreado en el dashboard
  del agente (`latency_p95`) con umbral de eval
  `AGENT_EVALS_LATENCY_THRESHOLD_MS`.

## Monitoring

- Dashboard del agente: latencia p95, errores, tool success, tokens y costo
  derivados de los registros (H4.1/H4.4).
- Regresiones de eval vinculadas a releases con gate estricto en señales
  deterministas y umbrales para costo/latencia (Q2).
- Alertas de costo: excesos de presupuesto registrados como
  `agent.budget_exhausted.v1` (sin PII).

## Compliance

- 0 PII en datasets, reportes, eventos y dashboard (FR-003, FR-016, FR-018).
- El tratamiento de datos con el proveedor cumple la politica de privacidad
  de la beta (datos redactados en golden dataset; retencion controlada).
