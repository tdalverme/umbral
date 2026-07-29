# API Endpoints

Esta tabla es un placeholder inicial para ordenar el contrato HTTP de Umbral. No implica que los endpoints esten implementados.

| Metodo | Ruta | Recurso | Proposito | Estado |
| --- | --- | --- | --- | --- |
| GET | `/health` | Sistema | Verificar disponibilidad basica del servicio. | Placeholder |
| GET | `/api/search-profiles` | Busquedas | Listar busquedas activas, pausadas o archivadas del usuario. | Placeholder |
| POST | `/api/search-profiles` | Busquedas | Crear una busqueda activa desde un brief estructurado. | Placeholder |
| GET | `/api/search-profiles/{search_profile_id}` | Busquedas | Obtener criterios, estado y politica de alertas de una busqueda. | Placeholder |
| PATCH | `/api/search-profiles/{search_profile_id}` | Busquedas | Actualizar criterios, tolerancias, zonas o politica de alertas. | Placeholder |
| GET | `/api/search-profiles/{search_profile_id}/matches` | Recomendaciones | Listar matches del radar con score, razones y riesgos. | Placeholder |
| POST | `/api/search-profiles/{search_profile_id}/feedback` | Feedback | Registrar like, dislike, save, dismiss u otra senal del usuario. | Placeholder |
| GET | `/api/listings/{listing_id}` | Listings | Obtener detalle, evidencia, fuente original y contexto urbano. | Placeholder |
| GET | `/api/listings/{listing_id}/explanation` | Explicaciones | Explicar por que un listing matchea o no con una busqueda. | Placeholder |
| POST | `/api/listings/compare` | Comparacion | Comparar varios listings dentro de una busqueda activa. | Placeholder |
| POST | `/api/chat/sessions` | Chat | Crear una conversacion contextual a una busqueda. | Placeholder |
| POST | `/api/chat/sessions/{session_id}/messages` | Chat | Enviar mensaje y ejecutar tools internas segun corresponda. | Placeholder |
| GET | `/api/notifications/preferences` | Notificaciones | Obtener preferencias de canal, frecuencia y horarios. | Placeholder |
| PATCH | `/api/notifications/preferences` | Notificaciones | Actualizar preferencias de notificacion. | Placeholder |

