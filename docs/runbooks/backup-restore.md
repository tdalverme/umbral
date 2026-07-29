# Backup y restore de foundation-runtime

## Alcance y responsables

La persona operadora de plataforma es responsable de verificar cada ejecución;
la persona de base de datos mantiene el dump lógico y la persona de datos
mantiene la réplica de objetos. El backup cubre PostgreSQL y las versiones
inmutables bajo `objects/`; Redis se excluye porque el outbox y los schedules
se reconstruyen desde PostgreSQL.

## Política

- Cadencia: cada 12 horas.
- RPO máximo: 24 horas (la cadencia deja margen operativo).
- Retención: 35 días con lock de retención en el bucket de recuperación.
- RTO máximo: 4 horas, restaurando beside-primary.
- Los buckets primario y de recuperación son privados; no se publican URLs ni
  ACLs.

Cada manifiesto contiene el hash de cada objeto y del dump, el head de Alembic,
counts opcionales, el punto de recuperación y su propio checksum. El manifiesto
se valida antes de copiar cualquier dato a la namespace nueva.

## Procedimiento

1. Crear un dump lógico cifrado y copiar las nuevas versiones inmutables al
   recovery bucket.
2. Escribir `manifest.json` y aplicar el lock de 35 días.
3. Crear una namespace nueva para el drill; nunca restaurar sobre `primary`.
4. Validar checksum del manifiesto, dump y todos los objetos; validar Alembic
   head y counts.
5. Ejecutar smoke y documentar punto de recuperación, duración y resultado.
6. Autorizar cutover sólo después de la validación; conservar la namespace
   original para rollback.

La implementación local usa `umbral.ops.backup.create_backup` y
`umbral.ops.restore.restore_backup`. El adapter remoto conserva las mismas
salidas, pero el drill MinIO/R2 requiere Docker o credenciales explícitas y no
forma parte del check local.

## Exclusiones y compensación

No se restauran colas Redis, caches, URLs firmadas, ACLs ni cuerpos fuera de
los objetos listados. Un objeto faltante o con checksum distinto detiene la
restauración; no se intenta borrar o sobrescribir el primario.
