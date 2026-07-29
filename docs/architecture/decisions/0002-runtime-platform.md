# ADR 0002: runtime platform

## Decision

Render Pro hosts the private API, worker, scheduler and PostgreSQL 17; the web
surface is a separate non-auto-build service. Cloudflare Access closes origins
and exposes only the exact `/health` path. R2 stores immutable object versions
and recovery manifests. Grafana Cloud/OTel and Sentry receive metadata-only
signals.

## Alternatives and tradeoffs

- A single provider would reduce coordination but loses the explicit edge gate
  and object retention controls required by this increment.
- Kubernetes adds HA and regional recovery before the beta needs it; it is
  deferred with single-region capacity limits.
- Redis remains disposable transport; PostgreSQL outbox state is rebuildable.

## Exit conditions

Revisit Render/Cloudflare/R2 when measured capacity, a second region, provider
outage frequency, or retention cost exceeds the beta budget. Promotion scripts
remain provider-neutral and record evidence without provider credentials.
