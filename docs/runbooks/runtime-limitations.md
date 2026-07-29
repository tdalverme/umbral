# Limitaciones aceptadas de foundation-runtime

- Beta single-region y single-instance; HA, multi-region y failover quedan
  fuera de este incremento.
- El check live de PostgreSQL, PostGIS, pgvector y MinIO necesita Docker y una
  `DATABASE_URL` explícita; el harness conserva gates offline/contractuales.
- Render, Cloudflare Access, R2, Grafana y Sentry remotos requieren proyectos,
  credenciales y aprobación operativa; los scripts no crean estado remoto por
  defecto.
- Spec Kit se ejecuta sólo si `.venv\Scripts\specify.exe` está instalado.
- El scheduler local es deliberadamente simple; calendarios y cron quedan para
  incrementos posteriores.
