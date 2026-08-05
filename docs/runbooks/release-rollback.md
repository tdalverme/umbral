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
