# ADR 0002: Session scoping de preferencias ("esta vez")

**Status**: Aceptado
**Date**: 2026-08-20
**Owner**: team-product
**Version**: 1.0.0
**Spec**: SPEC.md §19.3, §28.3, §28.6, §5 (SPEC global); conflicto con la
decision de `016-conversational-search-copilot` (el radar durable es la
verdad de producto).

## Context

SPEC.md define tres capas de preferencia: explicitas persistentes (§19.1),
aprendidas (§19.2) y **session overrides** (§19.3): ajustes temporales que
aplican solo a la busqueda o conversacion actual ("esta vez no me importa el
balcon", §28.3, §28.6). Ademas, §5 pide un fast path que rerankee y devuelva
resultados actualizados rapidamente tras un cambio de preferencia.

El repositorio decide en `016` que el estado durable del radar (no el
historial del chat) es la fuente de verdad: cada cambio de intencion se
versiona (`ProfileVersion`), se propone via HITL (`SearchProfileUpdateProposal`)
y se aplica por un servicio controlado. No existe ningun concepto de scope por
sesion ni de criterio efimero: proposta/confirmacion/version son el unico
camino de mutacion.

## Decision drivers

- Curso normal del codigo: cero abstraccion nueva para un caso de frecuencia
  desconocida (Constitucion IV: minimo codigo).
- Reversibilidad y trazabilidad: todo cambio de radar ya es versionado y
  auditable.
- Latencia: el repo ya separa respuesta inmediata (run previo con flag
  `stale`) de recomputacion async (<30s publicacion, spec 004).
- No duplicar fuentes de verdad de matching.

## Alternatives considered

| Alternativa | Costo | Riesgo | Resultado |
| --- | --- | --- | --- |
| Bindings temporales adosados al chat session (SPEC literal) | alto: tabla nueva, limpieza, segunda fuente de verdad para scoring | conflicto con "radar = verdad"; estado efimero sin audit | rechazada |
| Interpretar "esta vez" como edicion del radar (proposal + confirm + `ProfileVersion`) | bajo: reutiliza todo el mecanismo HITL existente | el cambio es durable (no efimero); la distincion desaparece del conversacional | **elegida** |
| Rechazar el caso por completo | nulo | experiencia bloqueada para lenguaje temporal | rechazada |

## Decision

1. **"Esta vez" se interpreta como edicion del radar**: el copiloto propone el
   cambio de criterio/binding y el usuario lo confirma (mismo flujo HITL de
   `propose_search_profile_update`/`propose_search_preference_update`); se
   crea un `ProfileVersion` nuevo y se agenda recomputo. El cambio es
   durable, reversible (supersesion) y auditable.
2. **La limitacion se muestra honestamente**: cuando el usuario marca
   temporalidad ("esta vez", "solo para esta busqueda"), la respuesta del
   agente aclara que el cambio queda aplicado al radar y puede revertirse,
   en vez de prometer un scope temporal que no existe.
3. **Session scoping real queda diferido** (backlog): se reintroduce como
   abstraccion propia solo si la frecuencia de lenguaje temporal o el
   comportamiento de reversiones lo justifican.
4. **Fast path §5**: se documenta como cubierto por la combinacion
   existente (respuesta inmediata con run previo + flag `stale`, publicacion
   async <30s). No se agrega rerank "preview" en V1.

## Consequences

- No hay estado efimero: el historial de versiones del radar conserva el
  cambio con trazabilidad completa.
- La distincion session/durable de SPEC.md queda anotada como adaptacion
  (no implementada en V1).
- El UX acepta una pequena ventana de resultados previos tras un cambio,
  acotada por el SLA de publicacion (<30s).

## Monitoring

- Frecuencia de lenguaje temporal ("esta vez", "solo para esta...") en
  trayectorias; si supera un umbral operacional, reabrir la decision.
- `latency` de publicacion de runs (objetivo <30s) como garantia del fast
  path.

## Compliance

- Sin cambios de scoring ni notification policy.
- Toda mutacion sigue el camino proposal -> confirm -> service -> version.