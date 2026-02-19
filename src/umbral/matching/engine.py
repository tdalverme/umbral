"""
Motor de matching entre usuarios y propiedades.

Implementa:
- Filtro Hard: Descarta propiedades fuera de criterios absolutos
- Filtro Vectorial: Calcula similitud semántica usuario-listing
- Personalización LLM: Genera análisis por usuario solo sobre umbral
"""

from dataclasses import dataclass
from typing import Optional

import structlog

from umbral.config import get_settings
from umbral.database import (
    UserRepository,
    RawListingRepository,
    NotificationRepository,
)
from umbral.models import UserPreferences
from umbral.analysis import EmbeddingGenerator, PersonalizedMatchAnalyzer

logger = structlog.get_logger()


@dataclass
class MatchResult:
    """Resultado de matching para un listing."""

    listing_id: str
    listing_data: dict
    similarity_score: float  # 0.0 a 1.0
    final_score: float  # Score final (actualmente igual a similarity_score)
    personalized_analysis: Optional[str] = None


class MatchingEngine:
    """
    Motor de matching con hard filters + similitud vectorial.

    Flujo:
    1. Obtener usuarios activos con onboarding completado
    2. Para cada usuario:
       a. Aplicar filtros hard (SQL) para pre-filtrar
       b. Calcular similitud semántica con embeddings
       c. Filtrar por threshold
       d. Generar análisis personalizado con LLM para los matches finales
       e. Notificar
    """

    def __init__(self):
        self.settings = get_settings()
        self.user_repo = UserRepository()
        self.listing_repo = RawListingRepository()
        self.notification_repo = NotificationRepository()
        self.embedding_generator = EmbeddingGenerator()
        self.personalized_analyzer = PersonalizedMatchAnalyzer()

    async def find_matches_for_user(
        self,
        user_id: str,
        preferences: UserPreferences,
        preference_vector: Optional[list[float]] = None,
        limit: int = 20,
    ) -> list[MatchResult]:
        """
        Encuentra propiedades que matchean con un usuario.

        Args:
            user_id: UUID del usuario
            preferences: Preferencias del usuario
            preference_vector: Embedding de preferencias (opcional)
            limit: Máximo de resultados

        Returns:
            Lista de MatchResult ordenados por score
        """
        hard = preferences.hard_filters

        # Paso 1: Filtros Hard (via SQL)
        listings = self.listing_repo.search_by_filters(
            operation_type=hard.operation_type,
            neighborhoods=hard.neighborhoods if hard.neighborhoods else None,
            limit=limit * 20,
        )

        if not listings:
            logger.info("No hay listings que cumplan filtros hard", user_id=user_id)
            return []

        # Paso 2: Filtrar los ya enviados
        results = []
        for listing in listings:
            listing_id = listing.get("id")

            # Verificar si ya se envió
            if self.notification_repo.was_sent(user_id, listing_id):
                continue

            features = listing.get("features", {}) or {}

            # Precio en USD (si viene en ARS, convertir para comparar filtros)
            price_usd = self._to_price_usd(
                raw_price=listing.get("price"),
                currency=listing.get("currency"),
            )
            if hard.min_price_usd is not None and price_usd < hard.min_price_usd:
                continue
            if hard.max_price_usd is not None and price_usd > hard.max_price_usd:
                continue

            rooms = self._to_int(listing.get("rooms"))
            if hard.min_rooms is not None and rooms < hard.min_rooms:
                continue
            if hard.max_rooms is not None and rooms > hard.max_rooms:
                continue

            # Filtros de requirements
            if hard.requires_balcony and not features.get("has_balcony"):
                continue
            if hard.requires_pets_allowed and not features.get("is_pet_friendly"):
                continue
            if hard.requires_furnished and not features.get("is_furnished"):
                continue
            if hard.requires_parking and not listing.get("parking_spaces"):
                continue

            results.append(listing)

        if not results:
            logger.info("No hay listings nuevos tras filtros", user_id=user_id)
            return []

        # Paso 3: Calcular scores
        matches = []
        for listing in results:
            # Similitud semántica
            similarity = await self._calculate_similarity(
                listing, preference_vector
            )

            # Score final vectorial
            final = similarity

            matches.append(
                MatchResult(
                    listing_id=listing["id"],
                    listing_data=listing,
                    similarity_score=similarity,
                    final_score=final,
                )
            )

        # Ordenar por score final
        matches.sort(key=lambda m: m.final_score, reverse=True)

        # Filtrar por threshold
        threshold = self.settings.similarity_threshold
        matches = [m for m in matches if m.final_score >= threshold]

        # Paso 4: Analisis LLM personalizado para los mejores candidatos
        personalized_threshold = self.settings.personalized_analysis_threshold
        for match in matches:
            if match.similarity_score >= personalized_threshold:
                match.personalized_analysis = await self.personalized_analyzer.generate(
                    preferences=preferences,
                    listing_data=match.listing_data,
                    similarity_score=match.similarity_score,
                )

        logger.info(
            "Matches encontrados",
            user_id=user_id,
            total=len(results),
            above_threshold=len(matches),
        )

        return matches[:limit]

    async def _calculate_similarity(
        self,
        listing: dict,
        preference_vector: Optional[list[float]],
    ) -> float:
        """
        Calcula similitud semántica entre preferencias del usuario y el listing.

        Compara el embedding de preferencias del usuario contra el
        embedding del texto crudo del listing.
        """
        if not preference_vector:
            return 0.5  # Sin vector, asumimos match medio

        # Matching vectorial contra embedding del texto crudo del listing
        listing_vector = listing.get("embedding_vector")
        if not listing_vector:
            return 0.5
        
        # Parsear listing_vector si viene como string
        if isinstance(listing_vector, str):
            import json
            try:
                listing_vector = json.loads(listing_vector)
            except json.JSONDecodeError:
                return 0.5
        
        # Asegurar que ambos son listas de floats
        if not isinstance(preference_vector, list) or not isinstance(listing_vector, list):
            return 0.5

        # Similitud de coseno
        try:
            similarity = EmbeddingGenerator.cosine_similarity(
                preference_vector, listing_vector
            )
            # Normalizar a 0-1 (coseno puede dar negativos)
            return max(0.0, min(1.0, (similarity + 1) / 2))
        except Exception as e:
            logger.warning(f"Error calculando similitud: {e}")
            return 0.5

    def _to_int(self, value) -> int:
        try:
            return int(str(value).strip())
        except (ValueError, TypeError):
            return 0

    def _to_price_usd(self, raw_price, currency) -> float:
        try:
            price = float(str(raw_price).replace(".", "").replace(",", "."))
        except (ValueError, TypeError):
            return 0.0
        if (currency or "").upper() == "USD":
            return price
        return price / self.settings.ars_to_usd_rate

    async def process_new_listings(
        self,
        listing_ids: Optional[list[str]] = None,
    ) -> dict:
        """
        Procesa nuevos listings y envía notificaciones.

        Args:
            listing_ids: IDs de listings a procesar (None = todos los nuevos)

        Returns:
            Estadísticas del procesamiento
        """
        from umbral.bot import UmbralBot

        stats = {
            "users_processed": 0,
            "matches_found": 0,
            "notifications_sent": 0,
            "errors": 0,
        }

        # Obtener usuarios activos
        active_users = self.user_repo.get_active_users()
        if not active_users:
            logger.info("No hay usuarios activos para notificar")
            return stats

        # Inicializar bot para enviar notificaciones
        bot = UmbralBot()

        for user in active_users:
            try:
                # Reconstruir preferencias desde el dict de la DB
                prefs_dict = user.get("preferences", {})
                hard_dict = prefs_dict.get("hard_filters", {})
                soft_dict = prefs_dict.get("soft_preferences", {})
                
                # Crear objetos de preferencias
                from umbral.models.user import HardFilters, SoftPreferences
                
                hard_filters = HardFilters(**hard_dict) if hard_dict else HardFilters()
                soft_preferences = SoftPreferences(**soft_dict) if soft_dict else SoftPreferences()
                
                preferences = UserPreferences(
                    hard_filters=hard_filters,
                    soft_preferences=soft_preferences,
                )

                preference_vector = user.get("preference_vector")
                
                # Parsear preference_vector si viene como string
                if preference_vector and isinstance(preference_vector, str):
                    import json
                    try:
                        preference_vector = json.loads(preference_vector)
                    except json.JSONDecodeError:
                        preference_vector = None

                # Buscar matches
                matches = await self.find_matches_for_user(
                    user_id=user["id"],
                    preferences=preferences,
                    preference_vector=preference_vector,
                    limit=3,  # Máximo 3 notificaciones por run
                )

                stats["users_processed"] += 1
                stats["matches_found"] += len(matches)

                # Enviar notificaciones
                for match in matches:
                    try:
                        success = await bot.send_listing_notification(
                            telegram_id=user["telegram_id"],
                            listing_data=match.listing_data,
                            similarity_score=match.final_score,
                            personalized_analysis=match.personalized_analysis or "No funcionó",
                        )

                        if success:
                            # Registrar notificación enviada
                            self.notification_repo.create(
                                user_id=user["id"],
                                listing_id=match.listing_id,
                                similarity_score=match.final_score,
                            )
                            stats["notifications_sent"] += 1

                    except Exception as e:
                        logger.error(
                            "Error enviando notificación",
                            user_id=user["id"],
                            error=str(e),
                        )
                        stats["errors"] += 1

            except Exception as e:
                import traceback
                logger.error(
                    "Error procesando usuario",
                    user_id=user.get("id"),
                    error=str(e),
                    traceback=traceback.format_exc(),
                )
                stats["errors"] += 1

        logger.info("Procesamiento de matching completado", **stats)
        return stats

    async def run_matching_cycle(self):
        """
        Ejecuta un ciclo completo de matching.

        Diseñado para ser llamado por GitHub Actions o cron.
        """
        logger.info("Iniciando ciclo de matching")

        try:
            stats = await self.process_new_listings()
            return stats
        except Exception as e:
            logger.error("Error en ciclo de matching", error=str(e))
            raise
