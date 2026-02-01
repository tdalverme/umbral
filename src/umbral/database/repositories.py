"""
Repositorios para operaciones CRUD en Supabase.

Cada repositorio maneja una tabla/entidad específica.
"""

from datetime import datetime
from typing import Optional

import structlog

from umbral.database.supabase_client import get_supabase_client, SupabaseClient
from umbral.models import (
    RawListing,
    AnalyzedListing,
    User,
    UserPreferences,
    HardFilters,
)
from umbral.models.user import SoftPreferences, UserFeedback

logger = structlog.get_logger()


class BaseRepository:
    """Clase base para repositorios."""

    def __init__(self, client: Optional[SupabaseClient] = None):
        self._client = client or get_supabase_client()

    @property
    def client(self) -> SupabaseClient:
        return self._client


class RawListingRepository(BaseRepository):
    """Repositorio para la capa Bronze (raw_listings)."""

    TABLE = "raw_listings"

    def create(self, listing: RawListing) -> dict:
        """
        Inserta un nuevo listing crudo.

        Returns:
            El registro insertado con su ID
        """
        data = listing.to_db_dict()
        response = self.client.table(self.TABLE).insert(data).execute()
        logger.info(
            "Raw listing creado",
            external_id=listing.external_id,
            source=listing.source,
        )
        return response.data[0] if response.data else {}

    def upsert(self, listing: RawListing) -> dict:
        """
        Inserta o actualiza un listing basado en source + external_id.

        Returns:
            El registro insertado/actualizado
        """
        data = listing.to_db_dict()
        response = (
            self.client.table(self.TABLE)
            .upsert(data, on_conflict="source,external_id")
            .execute()
        )
        logger.info(
            "Raw listing upserted",
            external_id=listing.external_id,
            source=listing.source,
        )
        return response.data[0] if response.data else {}

    def exists_by_hash(self, hash_id: str) -> bool:
        """Verifica si existe un listing con el mismo hash."""
        response = (
            self.client.table(self.TABLE)
            .select("id")
            .eq("hash_id", hash_id)
            .limit(1)
            .execute()
        )
        return len(response.data) > 0

    def get_by_id(self, listing_id: str) -> Optional[dict]:
        """Obtiene un listing por su UUID."""
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("id", listing_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_by_external_id(self, external_id: str, source: str) -> Optional[dict]:
        """Obtiene un listing por su ID externo y fuente."""
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("external_id", external_id)
            .eq("source", source)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_unanalyzed(self, limit: int = 100) -> list[dict]:
        """
        Obtiene listings que no han sido analizados aún.

        Returns:
            Lista de raw listings sin entrada en analyzed_listings
        """
        # Primero obtener IDs de listings ya analizados
        analyzed_response = (
            self.client.table("analyzed_listings")
            .select("raw_listing_id")
            .execute()
        )
        analyzed_ids = {r["raw_listing_id"] for r in analyzed_response.data}
        
        # Obtener raw listings
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .order("scraped_at", desc=True)
            .limit(limit * 2)  # Traer más para compensar los filtrados
            .execute()
        )
        
        # Filtrar los que no están analizados
        unanalyzed = [r for r in response.data if r["id"] not in analyzed_ids]
        
        logger.info(f"Raw listings: {len(response.data)}, Ya analizados: {len(analyzed_ids)}, Pendientes: {len(unanalyzed)}")
        
        return unanalyzed[:limit]

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Obtiene los listings más recientes."""
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .order("scraped_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data


class AnalyzedListingRepository(BaseRepository):
    """Repositorio para la capa Gold (analyzed_listings)."""

    TABLE = "analyzed_listings"

    def create(self, listing: AnalyzedListing) -> dict:
        """Inserta un nuevo listing analizado."""
        data = listing.to_db_dict()
        response = self.client.table(self.TABLE).insert(data).execute()
        logger.info(
            "Analyzed listing creado",
            external_id=listing.external_id,
            neighborhood=listing.neighborhood,
        )
        return response.data[0] if response.data else {}

    def update_embedding(self, listing_id: str, embedding: list[float]) -> bool:
        """Actualiza el vector de embedding de un listing."""
        response = (
            self.client.table(self.TABLE)
            .update({"embedding_vector": embedding})
            .eq("id", listing_id)
            .execute()
        )
        return len(response.data) > 0

    def update_vibe_embedding(self, listing_id: str, vibe_embedding: list[float]) -> bool:
        """
        Actualiza el vector de vibe embedding de un listing.
        
        Este embedding contiene solo executive_summary + style_tags
        para matching semántico de "vibe" con preferencias del usuario.
        """
        response = (
            self.client.table(self.TABLE)
            .update({"vibe_embedding": vibe_embedding})
            .eq("id", listing_id)
            .execute()
        )
        return len(response.data) > 0

    def update_embeddings(
        self,
        listing_id: str,
        embedding: list[float],
        vibe_embedding: list[float],
    ) -> bool:
        """Actualiza ambos embeddings en una sola operación."""
        response = (
            self.client.table(self.TABLE)
            .update({
                "embedding_vector": embedding,
                "vibe_embedding": vibe_embedding,
            })
            .eq("id", listing_id)
            .execute()
        )
        return len(response.data) > 0

    def get_by_raw_listing_id(self, raw_listing_id: str) -> Optional[dict]:
        """Obtiene el análisis de un raw listing específico."""
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("raw_listing_id", raw_listing_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_by_id(self, listing_id: str) -> Optional[dict]:
        """Obtiene un analyzed listing por su UUID."""
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("id", listing_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def search_by_filters(
        self,
        neighborhoods: Optional[list[str]] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_rooms: Optional[int] = None,
        max_rooms: Optional[int] = None,
        limit: int = 50,
    ) -> list[dict]:
        """
        Búsqueda por filtros hard.

        Returns:
            Lista de listings que cumplen los filtros
        """
        query = self.client.table(self.TABLE).select(
            "*, raw_listings(url, title, images, operation_type, features, description)"
        )

        if neighborhoods:
            query = query.in_("neighborhood", neighborhoods)
        if min_price is not None:
            query = query.gte("price_usd", min_price)
        if max_price is not None:
            query = query.lte("price_usd", max_price)
        if min_rooms is not None:
            query = query.gte("rooms", min_rooms)
        if max_rooms is not None:
            query = query.lte("rooms", max_rooms)

        response = query.order("analyzed_at", desc=True).limit(limit).execute()
        return response.data

    def get_for_user_matching(self, user_id: str) -> list[dict]:
        """
        Obtiene listings que matchean los filtros hard de un usuario.
        Usa la función RPC get_matching_listings_for_user.
        """
        response = self.client.client.rpc(
            "get_matching_listings_for_user",
            {"p_user_id": user_id}
        ).execute()
        return response.data

    def get_not_sent_to_user(self, user_id: str, limit: int = 20) -> list[dict]:
        """
        Obtiene listings analizados que no se han enviado al usuario.
        """
        response = (
            self.client.table(self.TABLE)
            .select(
                "*, raw_listings(url, title, images, operation_type)"
            )
            .not_.in_(
                "id",
                self.client.table("sent_notifications")
                .select("analyzed_listing_id")
                .eq("user_id", user_id)
            )
            .order("analyzed_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data


class UserRepository(BaseRepository):
    """Repositorio para usuarios."""

    TABLE = "users"

    def create(self, user: User) -> dict:
        """Crea un nuevo usuario."""
        data = user.to_db_dict()
        response = self.client.table(self.TABLE).insert(data).execute()
        logger.info(
            "Usuario creado",
            telegram_id=user.telegram_id,
            username=user.telegram_username,
        )
        return response.data[0] if response.data else {}

    def get_by_telegram_id(self, telegram_id: int) -> Optional[dict]:
        """Obtiene un usuario por su ID de Telegram."""
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_by_id(self, user_id: str) -> Optional[dict]:
        """Obtiene un usuario por su UUID."""
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def get_or_create(self, telegram_id: int, username: Optional[str] = None) -> dict:
        """Obtiene un usuario existente o crea uno nuevo."""
        existing = self.get_by_telegram_id(telegram_id)
        if existing:
            return existing

        user = User(telegram_id=telegram_id, telegram_username=username)
        return self.create(user)

    def update_preferences(
        self, telegram_id: int, preferences: UserPreferences
    ) -> dict:
        """Actualiza las preferencias de un usuario."""
        data = {
            "preferences": {
                "hard_filters": preferences.hard_filters.model_dump(),
                "soft_preferences": preferences.soft_preferences.model_dump(),
            },
            "updated_at": datetime.utcnow().isoformat(),
        }
        response = (
            self.client.table(self.TABLE)
            .update(data)
            .eq("telegram_id", telegram_id)
            .execute()
        )
        logger.info("Preferencias actualizadas", telegram_id=telegram_id)
        return response.data[0] if response.data else {}

    def update_onboarding_step(self, telegram_id: int, step: int) -> dict:
        """Actualiza el paso de onboarding del usuario."""
        data = {
            "onboarding_step": step,
            "onboarding_completed": step >= 5,  # 5 pasos en total
            "updated_at": datetime.utcnow().isoformat(),
        }
        response = (
            self.client.table(self.TABLE)
            .update(data)
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.data[0] if response.data else {}

    def complete_onboarding(self, telegram_id: int) -> dict:
        """Marca el onboarding como completado."""
        data = {
            "onboarding_completed": True,
            "updated_at": datetime.utcnow().isoformat(),
        }
        response = (
            self.client.table(self.TABLE)
            .update(data)
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.data[0] if response.data else {}

    def update_preference_vector(
        self, telegram_id: int, vector: list[float]
    ) -> dict:
        """Actualiza el vector de preferencia del usuario."""
        data = {
            "preference_vector": vector,
            "updated_at": datetime.utcnow().isoformat(),
        }
        response = (
            self.client.table(self.TABLE)
            .update(data)
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.data[0] if response.data else {}

    def increment_feedback_count(
        self, telegram_id: int, is_like: bool
    ) -> dict:
        """Incrementa el contador de likes o dislikes."""
        user = self.get_by_telegram_id(telegram_id)
        if not user:
            return {}

        field = "total_likes" if is_like else "total_dislikes"
        new_value = user.get(field, 0) + 1

        response = (
            self.client.table(self.TABLE)
            .update({field: new_value, "updated_at": datetime.utcnow().isoformat()})
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.data[0] if response.data else {}

    def get_active_users(self) -> list[dict]:
        """Obtiene todos los usuarios activos con onboarding completado."""
        response = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("is_active", True)
            .eq("onboarding_completed", True)
            .execute()
        )
        return response.data

    def set_active(self, telegram_id: int, is_active: bool) -> dict:
        """Activa o desactiva un usuario."""
        response = (
            self.client.table(self.TABLE)
            .update({
                "is_active": is_active,
                "updated_at": datetime.utcnow().isoformat()
            })
            .eq("telegram_id", telegram_id)
            .execute()
        )
        return response.data[0] if response.data else {}


class FeedbackRepository(BaseRepository):
    """Repositorio para feedback de usuarios."""

    TABLE = "user_feedback"

    def create(self, feedback: UserFeedback) -> dict:
        """Registra feedback de un usuario."""
        data = feedback.to_db_dict()
        response = (
            self.client.table(self.TABLE)
            .upsert(data, on_conflict="user_id,analyzed_listing_id")
            .execute()
        )
        logger.info(
            "Feedback registrado",
            user_id=feedback.user_id,
            listing_id=feedback.analyzed_listing_id,
            type=feedback.feedback_type,
        )
        return response.data[0] if response.data else {}

    def get_user_feedback(self, user_id: str) -> list[dict]:
        """Obtiene todo el feedback de un usuario."""
        response = (
            self.client.table(self.TABLE)
            .select("*, analyzed_listings(*)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data

    def get_liked_listings(self, user_id: str) -> list[dict]:
        """Obtiene los listings que el usuario marcó como interesantes."""
        response = (
            self.client.table(self.TABLE)
            .select("*, analyzed_listings(*)")
            .eq("user_id", user_id)
            .eq("feedback_type", "like")
            .execute()
        )
        return response.data


class NotificationRepository(BaseRepository):
    """Repositorio para notificaciones enviadas."""

    TABLE = "sent_notifications"

    def create(
        self,
        user_id: str,
        listing_id: str,
        similarity_score: float,
    ) -> dict:
        """Registra una notificación enviada."""
        data = {
            "user_id": user_id,
            "analyzed_listing_id": listing_id,
            "similarity_score": similarity_score,
        }
        response = (
            self.client.table(self.TABLE)
            .insert(data)
            .execute()
        )
        return response.data[0] if response.data else {}

    def was_sent(self, user_id: str, listing_id: str) -> bool:
        """Verifica si ya se envió una notificación."""
        response = (
            self.client.table(self.TABLE)
            .select("id")
            .eq("user_id", user_id)
            .eq("analyzed_listing_id", listing_id)
            .limit(1)
            .execute()
        )
        return len(response.data) > 0

    def get_user_history(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """Obtiene el historial de notificaciones de un usuario."""
        response = (
            self.client.table(self.TABLE)
            .select("*, analyzed_listings(*)")
            .eq("user_id", user_id)
            .order("sent_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
