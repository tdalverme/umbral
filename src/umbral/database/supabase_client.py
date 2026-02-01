"""
Cliente de Supabase.

Singleton para conexión a la base de datos.
"""

from functools import lru_cache
from typing import Optional

import structlog
from supabase import create_client, Client

from umbral.config import get_settings

logger = structlog.get_logger()


class SupabaseClient:
    """Wrapper del cliente de Supabase con métodos de utilidad."""

    def __init__(self, client: Client):
        self._client = client

    @property
    def client(self) -> Client:
        """Acceso directo al cliente de Supabase."""
        return self._client

    def table(self, name: str):
        """Acceso a una tabla específica."""
        return self._client.table(name)

    async def execute_rpc(
        self, function_name: str, params: Optional[dict] = None
    ) -> list:
        """
        Ejecuta una función RPC de PostgreSQL.

        Args:
            function_name: Nombre de la función en Supabase
            params: Parámetros de la función

        Returns:
            Lista de resultados
        """
        try:
            response = self._client.rpc(function_name, params or {}).execute()
            return response.data
        except Exception as e:
            logger.error(
                "Error ejecutando RPC",
                function=function_name,
                error=str(e),
            )
            raise

    def vector_search(
        self,
        table: str,
        embedding_column: str,
        query_vector: list[float],
        match_threshold: float = 0.85,
        match_count: int = 10,
        select_columns: str = "*",
    ) -> list:
        """
        Búsqueda vectorial usando similitud de coseno.

        Nota: Esta es una implementación simplificada.
        Para mejor rendimiento, usar la función RPC search_similar_listings.
        """
        # Supabase no tiene soporte nativo de vector search en el cliente Python
        # Usamos RPC para esto
        return self.client.rpc(
            "search_similar_listings",
            {
                "query_embedding": query_vector,
                "match_threshold": match_threshold,
                "match_count": match_count,
            },
        ).execute().data


@lru_cache
def get_supabase_client() -> SupabaseClient:
    """
    Obtiene el cliente de Supabase (singleton cacheado).

    Returns:
        SupabaseClient configurado

    Raises:
        ValueError: Si las credenciales no están configuradas
    """
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_key:
        raise ValueError(
            "SUPABASE_URL y SUPABASE_KEY son requeridos. "
            "Configura las variables de entorno."
        )

    # Usar service key si está disponible para operaciones admin
    key = settings.supabase_service_key or settings.supabase_key

    client = create_client(settings.supabase_url, key)
    logger.info("Cliente de Supabase inicializado", url=settings.supabase_url)

    return SupabaseClient(client)
