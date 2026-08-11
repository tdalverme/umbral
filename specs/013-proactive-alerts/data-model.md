# Data Model: Notificaciones y alertas proactivas (H5)

Migration `0013_notifications`. Shapes and validation rules; the golden
planner dataset and the notification policy live as published versioned
contracts (H3.4 convention), not DB tables.

## notification_preferences

Preferencias versionadas por usuario y por busqueda; cada cambio produce una
version (los registros previos no se mutan).

| Column | Type | Rules |
| --- | --- | --- |
| id | uuid PK | |
| user_id | uuid FK product_users | owner; 0 cross-access |
| search_profile_id | uuid FK search_profiles | |
| email_enabled | bool | default true |
| inbox_enabled | bool | default true |
| timezone | string(64) | zoneinfo valido; default America/Argentina/Buenos_Aires |
| quiet_hours_start | time | default 22:00 |
| quiet_hours_end | time | default 08:00 |
| digest_enabled | bool | default true (cadencia hibrida Q1) |
| digest_local_hour | int | default 9 |
| score_threshold | numeric(6,4) | umbral para new_match inmediato; 0 = todos inmediatos |
| state | enum active/paused/disabled | |
| version | int | incrementa por cambio; la firma del unsubscribe la incluye |
| created_at / updated_at | timestamptz | |

## notification_decisions

Decisiones del planner: persistidas, auditables, con dedupe.

| Column | Type | Rules |
| --- | --- | --- |
| id | uuid PK | |
| user_id | uuid FK | |
| search_profile_id | uuid FK | |
| recommendation_item_id | uuid FK recommendation_items | el item que origina la decision |
| trigger | enum new_match/price_drop | |
| reason_code | string(100) | notificado/duplicado/quiet_hours/fatiga/digest/descartado |
| reason_detail | string(500) nullable | sin PII |
| policy_version | string(100) | version de politica usada |
| preferences_version | int | version de preferencias usada |
| price_before / price_after | numeric nullable | solo price_drop |
| decision_state | enum immediate/digest/postponed/delivered/read/acted/duplicated/discarded | |
| duplicate_of_id | uuid FK self nullable | dedupe (FR-H5-006) |
| provider_message_id | string(200) nullable | idempotencia de entrega |
| created_at / updated_at | timestamptz | |

Indices: `(user_id, created_at)`, `(search_profile_id, created_at)`,
`(recommendation_item_id, trigger)` unico parcial (0 duplicados por
item+trigger), `(decision_state, digest_due_at)` para el duty de digest.

## notification_delivery_jobs

Reutiliza `job_executions` del runtime de jobs durables (H1-010): la
decision y el job `notifications.deliver` (target = decision id) se crean en
la misma transaccion (R-01). Lease, reintentos, reclaim y dead-letter son del
runtime existente; `provider_message_id` queda en la decision.

## notification_inbox_items

Vista web de las decisiones (misma fuente de verdad que el email).

| Column | Type | Rules |
| --- | --- | --- |
| id | uuid PK | |
| decision_id | uuid FK notification_decisions unico | 1:1 con la decision |
| user_id | uuid FK | |
| read_at | timestamptz nullable | |
| acted_at | timestamptz nullable | |
| created_at | timestamptz | |

## NotificationPolicy (contrato, no tabla)

`contracts/notifications/v1/notification-policy-v1.json` versionado e
inmutable: umbral de score inmediato, cooldown de fatiga (horas), ventana de
fatiga, digest hour default, max items por digest, 0 PII.

## PlannerGoldenDataset (contrato, no tabla)

`contracts/notifications/v1/planner-golden-v1.json`: casos con items,
historial, preferencias y policy → decision esperada (trigger, reason_code,
decision_state). Revisado por producto; gate estricto en el harness.

## Eventos (registry + 6)

`notification.decision_created.v1`, `notification.delivered.v1`,
`notification.delivery_failed.v1`, `notification.viewed.v1`,
`notification.acted.v1`, `notification.unsubscribed.v1` — 0 PII en payloads.

## State transitions

```
item nuevo/price drop
  -> planner -> duplicated | discarded | quiet_hours(postponed) | fatigue(postponed)
              | immediate -> pending_delivery -> delivered -> viewed -> acted
              | digest -> pending_digest -> (duty) -> delivered -> viewed -> acted
```
