# ADR 0002: runtime platform

## Decision

Render/Cloudflare remains the deferred production platform decision. For the
private beta only, Railway hosts the public web surface plus private API,
worker and scheduler services, its PostgreSQL (PostGIS/pgvector) and Redis, and
a single S3-compatible object storage bucket for immutable object versions and
backup manifests. Supabase remains the external proof-of-email identity
provider and Resend the transactional email provider; neither is Umbral
infrastructure. Railway private networking is automatic, so only web receives a
public Railway domain; no custom DNS is approved for this preview exception.
Grafana Cloud/OTel and Sentry receive metadata-only signals.

The preview exception has a USD 20 monthly ceiling. Serverless sleep is enabled
only for web and API; the worker remains available and scheduler work runs as a
UTC cron command no more frequently than every five minutes.

## Alternatives and tradeoffs

- The consolidated Railway topology (single Postgres URL, single object bucket)
  minimizes beta operating cost, but does not satisfy the production decision's
  custom DNS or approved availability posture; PostgreSQL is unmanaged and can
  be migrated to Neon later by changing only `DATABASE_URL`.
- Kubernetes adds HA and regional recovery before the beta needs it; it is
  deferred with single-region capacity limits.
- Redis remains disposable transport; PostgreSQL outbox state is rebuildable.

## Exit conditions

Exit the Railway preview exception before production promotion, custom DNS,
the USD 20 ceiling, measured capacity, a second region, provider outage
frequency, or retention cost requires a revisited platform decision. Promotion
scripts remain provider-neutral and record evidence without provider
credentials.
