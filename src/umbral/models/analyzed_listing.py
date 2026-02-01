"""
Capa Gold: AnalyzedListing

Modelo para almacenar datos normalizados y vectores de afinidad
listos para el motor de matching.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PropertyScores(BaseModel):
    """
    Puntajes cualitativos de 0.0 a 1.0 inferidos por IA.

    Estos scores representan el "valor invisible" del inmueble
    que no está explícito en los datos estructurados.
    """

    quietness: float = Field(
        ge=0, le=1, description="Nivel de silencio/tranquilidad esperado"
    )
    luminosity: float = Field(
        ge=0, le=1, description="Cantidad de luz natural esperada"
    )
    connectivity: float = Field(
        ge=0, le=1, description="Accesibilidad a transporte público"
    )
    wfh_suitability: float = Field(
        ge=0, le=1, description="Aptitud para trabajo remoto"
    )
    modernity: float = Field(
        ge=0, le=1, description="Nivel de modernidad/actualización"
    )
    green_spaces: float = Field(
        ge=0, le=1, description="Cercanía/acceso a espacios verdes"
    )


class InferredFeatures(BaseModel):
    """
    Atributos binarios y categóricos deducidos por IA
    a partir del análisis del texto y contexto.
    """

    is_investment_opportunity: bool = Field(
        default=False, description="Buena oportunidad de inversión"
    )
    is_family_friendly: bool = Field(
        default=False, description="Apto para familias con niños"
    )
    has_high_storage_capacity: bool = Field(
        default=False, description="Buena capacidad de almacenamiento"
    )
    neighborhood_vibe: str = Field(
        default="residencial",
        description="Ej: residencial, comercial, joven, trendy, lujo",
    )
    view_type: str = Field(
        default="interna",
        description="Ej: abierta, pulmón, frente, interna",
    )


class AnalyzedListing(BaseModel):
    """
    Capa Gold: Propiedad procesada y lista para el motor de matching.

    Esta clase se mapea directamente a la tabla 'analyzed_listings' en Supabase
    y contiene toda la inteligencia extraída por Gemini.
    """

    model_config = ConfigDict(from_attributes=True)

    # Identificadores
    id: Optional[str] = Field(None, description="UUID generado por Supabase")
    raw_listing_id: str = Field(..., description="FK al RawListing")
    external_id: str = Field(..., description="ID original del portal para joins rápidos")

    # Datos Económicos Normalizados
    currency_original: str = Field(..., description="Moneda original del anuncio")
    price_original: float = Field(..., description="Precio en moneda original")
    price_usd: float = Field(..., description="Precio convertido a USD")
    price_per_m2_usd: float = Field(
        default=0.0, description="Precio por m² en USD (métrica de valor)"
    )

    # Datos geográficos normalizados
    neighborhood: str = Field(..., description="Barrio normalizado")
    rooms: int = Field(..., description="Cantidad de ambientes como int")

    # Inteligencia Extraída
    scores: PropertyScores = Field(..., description="Puntajes cualitativos")
    features: InferredFeatures = Field(..., description="Características inferidas")
    style_tags: list[str] = Field(
        default_factory=list,
        description="Tags de estilo: ['luminoso', 'minimalista', 'acogedor']",
    )
    executive_summary: str = Field(
        ..., max_length=280, description="Resumen honesto tipo tweet"
    )

    # Búsqueda Semántica (pgvector)
    embedding_vector: Optional[list[float]] = Field(
        None, description="Vector de embedding completo del listing"
    )
    vibe_embedding: Optional[list[float]] = Field(
        None, description="Embedding solo de executive_summary + style_tags para matching de 'vibe'"
    )

    # Control de Versión
    analysis_version: str = Field(default="2.0", description="Versión del análisis")
    analyzed_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Timestamp del análisis",
    )

    def to_db_dict(self) -> dict:
        """Convierte a diccionario para inserción en Supabase."""
        data = self.model_dump(exclude={"id"})
        # Convertir nested models a dict para JSONB
        data["scores"] = self.scores.model_dump()
        data["features"] = self.features.model_dump()
        return data

    @classmethod
    def calculate_price_usd(
        cls, price: float, currency: str, exchange_rate: float
    ) -> float:
        """Convierte precio a USD."""
        if currency.upper() == "USD":
            return price
        return round(price / exchange_rate, 2)

    @classmethod
    def calculate_price_per_m2(
        cls, price_usd: float, size_m2: float
    ) -> float:
        """Calcula precio por metro cuadrado."""
        if size_m2 <= 0:
            return 0.0
        return round(price_usd / size_m2, 2)
