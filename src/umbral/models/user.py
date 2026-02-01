"""
Modelo de Usuario y Preferencias

Define las preferencias del usuario para el sistema de matching,
incluyendo filtros hard (excluyentes) y preferencias soft (ponderables).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class HardFilters(BaseModel):
    """
    Filtros excluyentes: si un listing no cumple, se descarta.
    Estos son los criterios no negociables del usuario.
    """

    # Precio
    min_price_usd: Optional[float] = Field(None, description="Precio mínimo en USD")
    max_price_usd: Optional[float] = Field(None, description="Precio máximo en USD")

    # Ubicación
    neighborhoods: list[str] = Field(
        default_factory=list, description="Lista de barrios aceptables"
    )

    # Características físicas
    min_rooms: Optional[int] = Field(None, ge=1, description="Mínimo de ambientes")
    max_rooms: Optional[int] = Field(None, ge=1, description="Máximo de ambientes")
    min_size_m2: Optional[float] = Field(None, description="Superficie mínima m²")

    # Tipo de operación
    operation_type: str = Field(
        default="alquiler", description="alquiler o venta"
    )

    # Características requeridas (must-have)
    requires_balcony: bool = Field(default=False)
    requires_parking: bool = Field(default=False)
    requires_pets_allowed: bool = Field(default=False)
    requires_furnished: bool = Field(default=False)


class SoftPreferences(BaseModel):
    """
    Preferencias ponderables: influyen en el score pero no excluyen.
    Representan el "ideal" del usuario.
    """

    # Pesos para los PropertyScores (0.0 a 1.0)
    weight_quietness: float = Field(default=0.5, ge=0, le=1)
    weight_luminosity: float = Field(default=0.5, ge=0, le=1)
    weight_connectivity: float = Field(default=0.5, ge=0, le=1)
    weight_wfh_suitability: float = Field(default=0.5, ge=0, le=1)
    weight_modernity: float = Field(default=0.5, ge=0, le=1)
    weight_green_spaces: float = Field(default=0.5, ge=0, le=1)

    # Descripción libre del usuario para matching semántico
    ideal_description: Optional[str] = Field(
        None,
        max_length=500,
        description="Descripción libre: 'Busco un depto luminoso y silencioso para trabajar desde casa'",
    )


class UserPreferences(BaseModel):
    """Combinación de filtros hard y preferencias soft."""

    hard_filters: HardFilters = Field(default_factory=HardFilters)
    soft_preferences: SoftPreferences = Field(default_factory=SoftPreferences)


class User(BaseModel):
    """
    Usuario del sistema con sus preferencias y estado de onboarding.
    """

    model_config = ConfigDict(from_attributes=True)

    # Identificadores
    id: Optional[str] = Field(None, description="UUID generado por Supabase")
    telegram_id: int = Field(..., description="ID único de Telegram")
    telegram_username: Optional[str] = Field(None, description="Username de Telegram")

    # Preferencias
    preferences: UserPreferences = Field(
        default_factory=UserPreferences, description="Preferencias del usuario"
    )

    # Vector de preferencia para matching semántico
    preference_vector: Optional[list[float]] = Field(
        None, description="Embedding de las preferencias para similitud"
    )

    # Estado
    is_active: bool = Field(default=True, description="Usuario activo para notificaciones")
    onboarding_completed: bool = Field(
        default=False, description="Completó el onboarding inicial"
    )
    onboarding_step: int = Field(
        default=0, description="Paso actual del onboarding (0-5)"
    )

    # Estadísticas de feedback
    total_likes: int = Field(default=0, description="Total de 'Me interesa'")
    total_dislikes: int = Field(default=0, description="Total de 'No me interesa'")

    # Metadatos
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Fecha de registro",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Última actualización",
    )

    def to_db_dict(self) -> dict:
        """Convierte a diccionario para inserción en Supabase."""
        data = self.model_dump(exclude={"id"})
        # Convertir nested models a dict para JSONB
        data["preferences"] = {
            "hard_filters": self.preferences.hard_filters.model_dump(),
            "soft_preferences": self.preferences.soft_preferences.model_dump(),
        }
        return data


class UserFeedback(BaseModel):
    """Feedback del usuario sobre un listing específico."""

    id: Optional[str] = Field(None, description="UUID generado por Supabase")
    user_id: str = Field(..., description="FK al User")
    analyzed_listing_id: str = Field(..., description="FK al AnalyzedListing")
    feedback_type: str = Field(
        ..., description="'like' o 'dislike'"
    )
    created_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )

    def to_db_dict(self) -> dict:
        """Convierte a diccionario para inserción en Supabase."""
        return self.model_dump(exclude={"id"})
