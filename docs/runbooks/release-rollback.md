# Release, promoción y rollback

1. Generar una sola manifest desde el commit y los digests `linux/amd64` con
   `scripts/deploy/build-release.ps1`.
2. Ejecutar el gate de acceso cerrado, comprobar backup/RPO y aplicar Alembic
   antes de desplegar las superficies.
3. Ejecutar smoke sintético de web/API/worker/scheduler, extensiones, reference
   job y objeto. No se usan datos de producto.
4. Mantener un lock por ambiente y registrar owner, release, gates y checksum.
5. Ante un smoke fallido, volver al digest/config snapshot anterior sólo si el
   schema es compatible; si no, detener y compensar hacia delante.

Los scripts son gates locales y no realizan una promoción remota implícita.
Railway (servicios, Postgres/Redis y object storage) y los proveedores de
identidad/correo se verifican mediante credenciales/proyectos del ambiente; la
ausencia de esos prerrequisitos queda registrada como brecha.

## Rollback de preview por digest

`scripts/deploy/rollback.ps1 -PreviousManifestPath <manifest-previo> -Environment preview`
restaura los digests inmutables del manifiesto anterior sin reconstruir:

1. Verifica compatibilidad de schema: el `database_revision` del manifiesto
   previo debe coincidir con el `alembic_version` desplegado. Nunca se hace
   downgrade de la base.
2. Vuelve web/API/worker/scheduler a los digests previos con
   `set-railway-images.ps1` y espera los deployments con
   `wait-railway-services.ps1`.
3. Ejecuta el smoke de preview completo contra el manifiesto restaurado.
4. Registra evidencia (`rollback-evidence.json`) con `schema_compatible`,
   `applied`, `smoke_result`, `elapsed_seconds` y los deployment IDs.

El rollback es válido sólo hacia un manifiesto que haya pasado el smoke
completo; no elimina usuarios, vínculos, roles ni auditoría de Umbral.
