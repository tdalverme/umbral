# ADR 0002: runtime platform

## Decision

Render/Cloudflare remains the deferred production platform decision. For the
private beta only, Railway hosts the public web surface plus private API,
worker and scheduler services; Neon provides PostgreSQL and Cloudflare R2
stores immutable object versions and recovery manifests. Railway private
networking is automatic, so only web receives a public Railway domain; no
custom DNS is approved for this preview exception. Grafana Cloud/OTel and
Sentry receive metadata-only signals.

The preview exception has a USD 20 monthly ceiling. Serverless sleep is enabled
only for web and API; the worker remains available and scheduler work runs as a
UTC cron command no more frequently than every five minutes.

## Alternatives and tradeoffs

- Railway/Neon/R2 minimize beta operating cost, but do not satisfy the
  production decision's custom DNS or approved availability posture.
- Kubernetes adds HA and regional recovery before the beta needs it; it is
  deferred with single-region capacity limits.
- Redis remains disposable transport; PostgreSQL outbox state is rebuildable.

## Exit conditions

Exit the Railway preview exception before production promotion, custom DNS,
the USD 20 ceiling, measured capacity, a second region, provider outage
frequency, or retention cost requires a revisited platform decision. Promotion
scripts remain provider-neutral and record evidence without provider
credentials.
