# Observabilidad y diagnóstico

Buscar recorridos por `correlation_id`, `request_id`, `release_id` y el
`route_template` registrado. Los logs, spans y Sentry comparten el filtro
cerrado; no se aceptan cuerpos, query strings, headers, URLs resueltas,
credenciales, excepciones ni claves de objetos.

Los códigos operativos son allowlisted (`postgres.unavailable`,
`queue.publish_failed`, `object.integrity_error`, entre otros) y reemplazan
mensajes de excepción. Si el exporter falla, la transacción continúa y la
superficie se degrada; no se reintenta enviando el payload rechazado.

El drill local usa `tests/contract/test_operational_signals.py` y
`tests/e2e/test_correlation_trace.py`. Grafana/Sentry remotos requieren
credenciales de la plataforma y no se declaran ejecutados en este checkout.
