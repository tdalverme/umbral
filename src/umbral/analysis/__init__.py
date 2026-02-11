"""
Módulo de análisis con IA.

Provee análisis de listings usando LLM (Gemini/Groq) y generación de embeddings.
"""

from umbral.analysis.listing_analyzer import ListingAnalyzer, GeminiAnalyzer, AnalysisResult
from umbral.analysis.embeddings import EmbeddingGenerator
from umbral.analysis.personalized_match_analyzer import PersonalizedMatchAnalyzer
from umbral.analysis.llm_providers import (
    get_llm_provider,
    BaseLLMProvider,
    GeminiProvider,
    GroqProvider,
    AVAILABLE_MODELS,
)

__all__ = [
    # Analizadores
    "ListingAnalyzer",
    "GeminiAnalyzer",  # Alias para compatibilidad
    "AnalysisResult",
    # Embeddings
    "EmbeddingGenerator",
    "PersonalizedMatchAnalyzer",
    # Proveedores LLM
    "get_llm_provider",
    "BaseLLMProvider",
    "GeminiProvider",
    "GroqProvider",
    "AVAILABLE_MODELS",
]
