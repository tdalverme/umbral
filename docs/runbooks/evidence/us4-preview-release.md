# Evidencia US4 preview

Estado: preparado localmente; no ejecutado contra Render/Cloudflare.

- Manifest: `scripts/deploy/build-release.ps1` genera checksum y dos digests.
- Access gate: `scripts/deploy/verify-access.ps1` exige origin cerrado y único
  bypass `/health`.
- Migration/smoke/promotion: gates ordenados y evidencia JSON sin credenciales.
- Brecha: requiere proyecto preview persistente y secretos de plataforma.
