# Evolución de datos

La base de datos de runtime usa PostgreSQL 17 con `postgis` y `vector`. La
aplicación no ejecuta migraciones al arrancar: la promoción aplica Alembic
antes de iniciar las superficies y registra la revisión anterior, la nueva y
el resultado.

## Bootstrap y upgrade

Desde un checkout con el entorno Python activo:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://umbral:umbral_local_only@localhost:5432/umbral"
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
.venv\Scripts\python.exe -m alembic check
```

`0001_foundation_runtime` crea las siete tablas de foundation en una única
revisión lineal y verifica las extensiones requeridas. El downgrade sólo está
declarado para una base vacía; una base con datos se compensa con una revisión
forward y no se destruye.

## Transacciones y bloqueo optimista

Cada operación abre un único `Session` mediante el transaction manager. Los
repositorios pueden hacer `flush`, pero no tienen método de commit. Un fallo
sale por rollback y close. Las filas mutables llevan `version`; el `UPDATE`
incluye la versión esperada y un conteo de filas distinto de uno se traduce a
`concurrency.conflict` sin sobrescribir el valor más nuevo.

La creación de ejecución/outbox y el avance de schedule son una sola
transacción. Publicación en Redis y escritura de bytes en object storage
ocurren fuera de ella y tienen reconciliación explícita.

## Verificación y compensación

`scripts/check-migrations.ps1` valida el head único y el inventario de metadata
sin abrir una conexión. Con `DATABASE_URL` configurado agrega `alembic check`
contra la base. Los probes de persistencia sólo exponen nombres y códigos
allowlisted (`postgres.*`, `postgis.*`, `pgvector.*`, `alembic.*`); nunca
devuelven URLs, credenciales, SQL ni excepciones.

