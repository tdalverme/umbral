# API Endpoints

Esta tabla separa la superficie operativa implementada de las rutas de
producto futuras. Las rutas operativas son side-effect-free y no exponen
secretos ni hosts privados.

| Metodo | Ruta | Recurso | Proposito | Estado |
| --- | --- | --- | --- | --- |
| GET | `/health` | Sistema | Verificar disponibilidad basica del servicio. | Implementado |
| GET | `/ready` | Sistema | Reportar readiness sanitizada de la superficie. | Implementado |
| GET | `/version` | Sistema | Publicar release, manifest, contrato y revision de DB. | Implementado |
| GET | `/api/v1/search-profiles` | Busquedas | Listar busquedas activas, pausadas o archivadas del usuario. | Implementado |
| POST | `/api/v1/search-profiles` | Busquedas | Crear una busqueda activa desde un brief estructurado. | Implementado |
| GET | `/api/v1/search-profiles/{id}` | Busquedas | Obtener criterios, estado, politica inicial y ultimo run. | Implementado |
| PATCH | `/api/v1/search-profiles/{id}` | Busquedas | Actualizar criterios con `expected_version` (409 tipado en concurrencia). | Implementado |
| POST | `/api/v1/search-profiles/{id}/status` | Busquedas | Pausar, reanudar o archivar una busqueda. | Implementado |
| GET | `/api/v1/search-profiles/{id}/matches` | Recomendaciones | Listar matches persistentes del run (score, contribuciones, punto autorizado, resumen del listing). | Implementado |
| GET | `/api/v1/search-profiles/{id}/preferences` | Preferencias | Inspeccionar deseos expresados, vinculaciones, confianza y limitaciones del radar (feature 016). | Implementado |
| GET | `/api/v1/listings/{listing_id}` | Listings | Obtener detalle, atributos, faltantes, cambios conocidos y fuente (autorizado via runs del usuario). | Implementado |
| POST | `/api/v1/product-events` | Eventos | Registrar eventos versionados de producto emitidos por el cliente (impresion, vista, fuente abierta). | Implementado |
| POST | `/api/v1/search-profiles/{id}/feedback` | Feedback | Registrar like, dislike, save, dismiss u otra senal del usuario. | Futuro (H3) |
| GET | `/api/v1/listings/{id}/explanation` | Explicaciones | Explicar por que un listing matchea o no con una busqueda. | Futuro (H3) |
| POST | `/api/v1/listings/compare` | Comparacion | Comparar varios listings dentro de una busqueda activa. | Futuro (H3) |
| POST | `/api/v1/chat/sessions` | Chat | Crear una conversacion contextual a una busqueda. | Futuro (H4) |
| POST | `/api/v1/chat/sessions/{id}/messages` | Chat | Enviar mensaje y ejecutar tools internas segun corresponda. | Futuro (H4) |
| GET | `/api/v1/notifications/preferences` | Notificaciones | Obtener preferencias de canal, frecuencia y horarios. | Futuro (H5) |
| PATCH | `/api/v1/notifications/preferences` | Notificaciones | Actualizar preferencias de notificacion. | Futuro (H5) |
