"""
Capa Bronze: RawListing

Modelo para almacenar el estado original de los anuncios
sin transformación para auditoría y re-procesamiento.
"""

import hashlib
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class ListingFeatures(BaseModel):
    """Características booleanas extraídas del anuncio."""

    is_furnished: bool = False
    is_pet_friendly: bool = False
    has_security: bool = False
    has_elevator: bool = False
    has_gas: bool = False
    has_air_conditioning: bool = False
    has_heating: bool = False
    has_laundry: bool = False
    has_sum: bool = False  # Salón de Usos Múltiples
    has_bbq: bool = False
    has_pool: bool = False
    has_gym: bool = False
    has_balcony: bool = False
    has_terrace: bool = False
    has_garden: bool = False
    has_patio: bool = False


class RawListing(BaseModel):
    """
    Capa Bronze: Anuncio crudo directamente del scraper.

    Este modelo preserva los datos originales del portal para:
    - Auditoría y trazabilidad
    - Re-procesamiento con nuevos prompts de IA
    - Detección de cambios en anuncios existentes
    """

    # Identificación
    external_id: str = Field(..., description="ID único del portal origen")
    url: str = Field(..., description="URL completa del anuncio")
    source: str = Field(..., description="Portal origen: mercadolibre, zonaprop, argenprop")

    # Contenido textual
    title: str = Field(..., description="Título del anuncio")
    description: str = Field(..., description="Descripción completa")

    # Precio (strings originales sin normalizar)
    price: str = Field(..., description="Precio como string original")
    currency: str = Field(..., description="Moneda: USD o ARS")

    # Ubicación
    location: str = Field(..., description="Ubicación completa como texto")
    region: str = Field(default="CABA", description="Región/Provincia")
    city: str = Field(default="Buenos Aires", description="Ciudad")
    neighborhood: str = Field(..., description="Barrio")

    # Características físicas (strings para preservar formato original)
    rooms: str = Field(..., description="Cantidad de ambientes")
    bathrooms: str = Field(default="1", description="Cantidad de baños")
    size_total: str = Field(default="", description="Superficie total m²")
    size_covered: str = Field(default="", description="Superficie cubierta m²")

    # Atributos opcionales
    age: Optional[str] = Field(None, description="Antigüedad del inmueble")
    disposition: Optional[str] = Field(None, description="Frente, contrafrente, lateral")
    orientation: Optional[str] = Field(None, description="Norte, Sur, Este, Oeste")
    maintenance_fee: Optional[str] = Field(None, description="Expensas")
    operation_type: Optional[str] = Field("alquiler", description="alquiler o venta")

    # Media
    images: Optional[list[str]] = Field(default_factory=list, description="URLs de imágenes")
    coordinates: Optional[dict] = Field(None, description="{'lat': float, 'lng': float}")

    # Extras
    parking_spaces: Optional[int] = Field(None, description="Cantidad de cocheras")
    features: ListingFeatures = Field(
        default_factory=ListingFeatures, description="Características booleanas"
    )
    embedding_vector: Optional[list[float]] = Field(
        default=None, description="Embedding semántico del texto crudo del listing"
    )

    # Metadatos
    scraped_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Timestamp de scraping ISO",
    )

    @computed_field
    @property
    def hash_id(self) -> str:
        """
        Hash único para detectar duplicados y cambios.
        Basado en: título + precio + descripción (primeros 500 chars)
        """
        content = f"{self.title}|{self.price}|{self.description[:500]}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def to_db_dict(self) -> dict:
        """Convierte a diccionario para inserción en Supabase."""
        data = self.model_dump()
        # Convertir features a dict para JSONB
        data["features"] = self.features.model_dump()
        return data
