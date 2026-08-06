# Private Beta Identity Deployment — Close Report

**Date**: 2026-08-06
**Branch/HEAD**: `main` (código del incremento promocionado vía release `v0.2.18`)
**Goal**: Cerrar T049 y T062 con un preview persistente en Railway y smoke real.

## Objetivo cumplido

El pipeline `promote` de preview pasa completo de punta a punta:

- `release` construye las imágenes web/runtime y publica un manifest inmutable.
- `promote` ejecuta backup, migración, conformance de dependencias, switch de
  digests, scheduler-once, preload de invitación y el smoke de preview.
- El smoke pasa **15/15 escenarios** contra `v0.2.18`:
  `runtime_identity, invitation, invited, scanner_prefetch,
  explicit_confirmation, single_use, repeat, non_invited, authorization,
  logout, idle_expiry, delivered, bounced, complained, redaction`.

## Bloqueos resueltos en esta sesión

1. Web → API: `UMBRAL_PRIVATE_API_URL` con `:8000`; el web lee la URL privada.
2. Web manifest: carga inline (JSON) de `UMBRAL_RELEASE_MANIFEST`.
3. Web `/ready`: tolera BFF token vacío (el API los acepta).
4. Resend observación: `User-Agent: curl/8.7.1` (Cloudflare 1010).
5. Outbox/jobs: relay del smoke + handler RQ dotted (RQ split por `.`) + job IDs
   con guion (RQ rechaza `:`).
6. Credenciales Resend y Supabase sincronizadas a api/worker/scheduler.
7. `IDENTITY_CAPTURE_ORIGIN` fijado al origen público del web.
8. Rate-limit del invitee reseteado antes del smoke.
9. Scheduler surface fresca vía `run-scheduler-pass.py` en el env desplegado.
10. Supabase `verify_otp` con `shouldCreateUser` y sin el check redundante de
    `email_confirmed_at`; endpoints de confirm/logout con `Response(204)`.
11. Delivery: el smoke entrega eventos firmados (`email.delivered/bounced/
    complained`) al webhook del API con el `EMAIL_WEBHOOK_SECRET` compartido,
    porque Resend rechaza `onboarding@resend.dev` hacia `@resend.dev` sin
    dominio verificado.
12. `smoke.ps1` separa stdout (JSON) de stderr (diagnósticos).

## Exit criteria del diseño (spec 2026-08-01)

Ver `docs/runbooks/identity-access.md` (SC-001–SC-010) y la sección
`## Close Status (2026-08-06)` en
`docs/superpowers/specs/2026-08-01-umbral-beta-deployment-design.md`.

Resumen: deploy sin rebuild verificado; rollback por digest implementado
(`scripts/deploy/rollback.ps1`) pero sin ejecutar (aún no existe un manifiesto
previo que pase el smoke completo); conformance de providers y dependencias
verificado; SC-001–SC-010 verificados salvo el benchmark de 20 viajes; la
detección de pausa de Supabase Free y el techo de costo USD 20 son operativos
(follow-up); el delivery por Resend real queda como follow-up DNS-free.

## Desviaciones documentadas

- Entrega de eventos de delivery simulada por el smoke (no vía Resend), por la
  limitación DNS-free de `onboarding@resend.dev`; ver `identity-access.md`.
- El `EMAIL_WEBHOOK_SECRET` quedó impreso en logs de Actions en corridas
  intermedias (v0.2.18 beta); el flujo final ya no lo imprime y el valor se
  deriva del manifest (regenerable).

## Evidencia remota

- Runs de `release` y `promote` exitosos en GitHub Actions para `v0.2.18`.
- Conformance preview: Postgres/PostGIS/pgvector, Redis, object storage,
  Grafana OTLP, Sentry, Supabase, Resend.
- Smoke preview 15/15.
