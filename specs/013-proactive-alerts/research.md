# Research: Notificaciones y alertas proactivas (H5)

Decisions, rationale and rejected alternatives for UM-H5-001..UM-H5-020.

## R-01: Transactional outbox — reutilizar el runtime de jobs durables

- **Decision**: Las decisiones de notificacion y su entrega se persisten y
  confirman atomicamente con el runtime de jobs durables existente (H1-010:
  `job_executions` con lease, reclaim, reap, relay_due y RQ worker). El
  "outbox transaccional" del FR-H5-011 es el outbox de job executions ya
  operativo: la decision y el job `notifications.deliver` se crean en la
  misma transaccion; el scheduler reclaima expirados, reenvia y el worker RQ
  entrega con provider message id.
- **Rationale**: 0 infraestructura nueva; el outbox/lease/backoff/dead-letter
  ya estan probados (identity.magic_link.issue usa el mismo mecanismo);
  cumple FR-H5-011/012 sin tablas nuevas de outbox.
- **Alternatives considered**:
  - Tabla `outbox_messages` propia con worker dedicado: mas codigo y un
    segundo mecanismo de lease en el repo (rechazado).
  - Redis stream como outbox: pierde la atomicidad con Postgres y agrega un
    canal durable nuevo (rechazado).

## R-02: Email — reutilizar el cliente Resend compartido

- **Decision**: `application/notifications/ports.py` define
  `NotificationEmailPort`; la infra usa el mismo cliente Resend del ADR 0003
  (mismo `RESEND_API_KEY`), con sender/from propio de notificaciones y el
  mismo fake `recording` en local. La redaccion del template vive en
  infraestructura y solo recibe los campos de la decision persistida
  (0 afirmaciones libres).
- **Rationale**: un solo proveedor transaccional en beta (ADR 0003); el
  adapter de identity ya clasifica errores Resend; el fake recording ya
  permite E2E local.
- **Alternatives considered**: SES/Postmark nuevo: segundo proveedor y
  segundo contrato de credenciales (rechazado); notificaciones push/PWA:
  fuera de alcance de beta (Q3 del spec).

## R-03: Cadencia hibrida — planner puro + digest como duty programada

- **Decision**: El planner es una funcion pura
  (`PlanNotifications(item, historia, preferencias, policy) -> decision con
  razon/codigo`). La cadencia la decide el trigger: `price_drop` y
  `new_match` con score >= umbral de politica son inmediatos; el resto queda
  `pending_digest`. Un duty programado (`notifications.digest`) agrupa los
  pending_digest del dia a las 9:00 de la timezone del usuario y genera la
  entrega agrupada sin alterar scores (UM-H5-009, P0 por Q1).
- **Rationale**: mantiene el planner deterministico y testeable (misma
  convencion golden que matching/evals); el digest es un agrupamiento puro
  sobre decisiones ya tomadas (0 recalculado).
- **Alternatives considered**: planner con politica de cadencia por item en
  el scheduler: mezcla decision y agrupacion (rechazado).

## R-04: Planner deterministico — dataset golden propio

- **Decision**: `contracts/notifications/v1/planner-golden-v1.json` con
  casos golden (nuevo match, price drop, duplicado, quiet hours, fatiga,
  digest, combinaciones) revisados por producto; gate de regresiones estricto
  en el harness (`check-alerts.ps1`), misma convencion que matching (H3.4) y
  agent evals (H4.4).
- **Rationale**: el planner decide interrupciones al usuario (Principio II:
  decisiones deterministas y auditables); sin golden no hay confianza para
  cambiar umbrales.
- **Alternatives considered**: LLM en la decision de notificar (rechazado por
  constitucion: 0 ranking/decisiones generativas).

## R-05: Quiet hours y timezone — zoneinfo por preferencia

- **Decision**: `zoneinfo.ZoneInfo` por usuario desde sus preferencias;
  default `America/Argentina/Buenos_Aires`. Quiet hours default 22:00-08:00.
  La decision guarda `scheduled_for` en UTC y el estado `postponed` con la
  razon; el duty de digest/reenvio materializa los pospuestos.
- **Rationale**: calculo puro y testeable con fechas fijas; 0 dependencia de
  la hora del servidor para decisiones (solo el scheduler materializa).
- **Alternatives considered**: quiet hours en el scheduler (mezcla logica y
  tiempo del servidor; rechazado).

## R-06: Unsubscribe token — HMAC estatal sin tabla

- **Decision**: token = `HMAC(SECRET, user_id|search_id|pref_version, exp)`
  con expiracion (24h); el endpoint de baja valida, actualiza preferencias,
  emite `notification.unsubscribed.v1` y el token queda inservible por
  version (la firma incluye la version vigente).
- **Rationale**: 0 tabla nueva, expirable, auditable y sin login (FR-H5-017).
- **Alternatives considered**: token persistido con intentos (tabla y
  limpieza; rechazado por mas codigo).

## R-07: Vistas y acciones — eventos via API del inbox

- **Decision**: las vistas/acciones se emiten desde la web (inbox) y desde
  los CTA del email (links a la web que marcan viewed/acted con el
  `decision_id`); 0 pixel de tracking en email. Eventos
  `notification.viewed.v1` / `notification.acted.v1` alimentan precision
  percibida.
- **Rationale**: el inbox web es un canal de primera clase (Q3); el click en
  el email aterriza en la web y emite el mismo evento.
- **Alternatives considered**: pixel de email (0 beneficio con inbox web y
  PII de tracking; rechazado).

## R-08: Fatiga — cooldown deterministico por ventana

- **Decision**: cooldown por ventana (default 6h) basado en entregas recientes
  sin interaccion (vista/accion); configurable por politica versionada;
  aplicado por usuario y por busqueda con suma documentada.
- **Rationale**: simple, deterministico y medible con el historial de
  decisiones (0 heuristica generativa).
- **Alternatives considered**: umbral adaptativo por engagement (complejidad
  sin necesidad de beta; rechazado).
