# API Endpoints

Esta tabla separa la superficie operativa implementada de las rutas de
producto futuras. Las rutas operativas son side-effect-free y no exponen
secretos ni hosts privados.

| Metodo | Ruta | Recurso | Proposito | Estado |
| --- | --- | --- | --- | --- |
| GET | `/health` | Sistema | Verificar disponibilidad basica del servicio. | Implementado |
| GET | `/ready` | Sistema | Reportar readiness sanitizada de la superficie. | Implementado |
| GET | `/version` | Sistema | Publicar release, manifest, contrato y revision de DB. | Implementado |
| GET | `/api/search-profiles` | Busquedas | Listar busquedas activas, pausadas o archivadas del usuario. | Futuro |
| POST | `/api/search-profiles` | Busquedas | Crear una busqueda activa desde un brief estructurado. | Futuro |
| GET | `/api/search-profiles/{search_profile_id}` | Busquedas | Obtener criterios, estado y politica de alertas de una busqueda. | Futuro |
| PATCH | `/api/search-profiles/{search_profile_id}` | Busquedas | Actualizar criterios, tolerancias, zonas o politica de alertas. | Futuro |
| GET | `/api/search-profiles/{search_profile_id}/matches` | Recomendaciones | Listar matches del radar con score, razones y riesgos. | Futuro |
| POST | `/api/search-profiles/{search_profile_id}/feedback` | Feedback | Registrar like, dislike, save, dismiss u otra senal del usuario. | Futuro |
| GET | `/api/listings/{listing_id}` | Listings | Obtener detalle, evidencia, fuente original y contexto urbano. | Futuro |
| GET | `/api/listings/{listing_id}/explanation` | Explicaciones | Explicar por que un listing matchea o no con una busqueda. | Futuro |
| POST | `/api/listings/compare` | Comparacion | Comparar varios listings dentro de una busqueda activa. | Futuro |
| POST | `/api/chat/sessions` | Chat | Crear una conversacion contextual a una busqueda. | Futuro |
| POST | `/api/chat/sessions/{session_id}/messages` | Chat | Enviar mensaje y ejecutar tools internas segun corresponda. | Futuro |
| GET | `/api/notifications/preferences` | Notificaciones | Obtener preferencias de canal, frecuencia y horarios. | Futuro |
| PATCH | `/api/notifications/preferences` | Notificaciones | Actualizar preferencias de notificacion. | Futuro |
