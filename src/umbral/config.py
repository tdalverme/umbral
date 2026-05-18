"""
Configuración centralizada del sistema.
Carga variables de entorno y define settings globales.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Encontrar la raíz del proyecto (donde está el .env)
# config.py -> umbral/ -> src/ -> umbral (project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Configuración principal de la aplicación."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Supabase
    supabase_url: str = Field(..., description="URL del proyecto Supabase")
    supabase_key: str = Field(..., description="Anon key de Supabase")
    supabase_service_key: Optional[str] = Field(
        None, description="Service role key para operaciones admin"
    )

    # LLM Provider
    llm_provider: str = Field(
        "groq",
        description="Proveedor de LLM a usar: 'gemini' o 'groq'"
    )
    
    # Gemini
    gemini_api_key: Optional[str] = Field(None, description="API key de Google Gemini")
    gemini_model: str = Field("gemini-2.0-flash", description="Modelo de Gemini a usar")
    embedding_model: str = Field(
        "gemini-embedding-2-preview",
        description="Modelo de embedding (Gemini) para listings y preferencias",
    )
    embedding_output_dim: int = Field(
        768,
        ge=128,
        le=3072,
        description="Dimensión Matryoshka solicitada al modelo de embeddings",
    )
    embedding_storage_dim: int = Field(
        768,
        ge=128,
        le=3072,
        description="Dimensión final persistida en DB (padding/truncado si aplica)",
    )
    embedding_max_images: int = Field(
        4,
        ge=0,
        le=10,
        description="Máximo de imágenes principales usadas para embedding multimodal",
    )
    embedding_image_timeout_seconds: float = Field(
        8.0,
        ge=1.0,
        le=30.0,
        description="Timeout por descarga de imagen para embedding multimodal",
    )
    
    # Groq
    groq_api_key: Optional[str] = Field(None, description="API key de Groq")
    groq_model: str = Field(
        "llama-3.1-8b-instant",
        description=(
            "Modelo de Groq a usar. Para run_analysis conviene un modelo de texto "
            "como llama-3.1-8b-instant o llama-3.3-70b-versatile."
        )
    )

    # Telegram
    telegram_bot_token: str = Field(..., description="Token del bot de Telegram")
    telegram_webhook_url: Optional[str] = Field(
        None, description="URL pública base para webhook (ej: https://app.onrender.com)"
    )
    telegram_webhook_path: str = Field(
        "telegram", description="Path del webhook (sin / inicial)"
    )
    telegram_webhook_listen: str = Field(
        "0.0.0.0", description="Host de escucha para webhook"
    )

    # Feedback learning rate
    feedback_learning_rate: float = Field(
        0.1, ge=0.0, le=1.0, description="Learning rate para feedback like/dislike"
    )

    # Scraping
    scrape_delay_min: float = Field(2.0, description="Delay mínimo entre requests (segundos)")
    scrape_delay_max: float = Field(5.0, description="Delay máximo entre requests (segundos)")
    max_pages_per_run: int = Field(10, description="Máximo de páginas a scrapear por ejecución")

    # Matching
    similarity_threshold: float = Field(
        0.75, ge=0.0, le=1.0, description="Umbral de similitud para notificaciones"
    )
    personalized_analysis_threshold: float = Field(
        0.75,
        ge=0.0,
        le=1.0,
        description="Umbral de similitud para ejecutar analisis LLM personalizado",
    )

    # Exchange Rate
    ars_to_usd_rate: float = Field(1000.0, description="Tipo de cambio ARS/USD")

    # Logging
    log_level: str = Field("INFO", description="Nivel de logging")

    # Internal admin
    admin_api_key: Optional[str] = Field(
        None,
        description="API key opcional para proteger endpoints internos /admin",
    )

    # Analysis versioning
    analysis_version: str = Field("2.0", description="Versión del análisis de IA")


@lru_cache
def get_settings() -> Settings:
    """Obtiene la configuración cacheada."""
    return Settings()


# Constantes del sistema
CABA_NEIGHBORHOODS = [
    "Palermo",
    "Belgrano",
    "Recoleta",
    "Caballito",
    "Almagro",
    "Villa Crespo",
    "Colegiales",
    "Nuñez",
    "Villa Urquiza",
    "Saavedra",
    "Devoto",
    "Villa del Parque",
    "Flores",
    "Floresta",
    "Once",
    "Balvanera",
    "San Telmo",
    "La Boca",
    "Barracas",
    "Constitución",
    "Monserrat",
    "San Nicolás",
    "Retiro",
    "Puerto Madero",
    "Boedo",
    "Parque Patricios",
    "Pompeya",
    "Mataderos",
    "Liniers",
    "Versalles",
    "Villa Luro",
    "Vélez Sarsfield",
    "Monte Castro",
    "Villa Real",
    "Villa Pueyrredón",
    "Agronomía",
    "Paternal",
    "Villa Ortúzar",
    "Chacarita",
    "Villa Santa Rita",
    "Villa General Mitre",
    "Parque Chas",
    "Villa Devoto",
    "Villa Lugano",
    "Villa Riachuelo",
    "Villa Soldati",
    "Parque Avellaneda",
    "Parque Chacabuco",
    "Coghlan",
]

OPERATION_TYPES = ["alquiler", "venta"]

CURRENCY_CODES = ["USD", "ARS"]
