"""
Abstracción de proveedores LLM.

Permite switchear fácilmente entre diferentes proveedores (Gemini, Groq)
sin cambiar el código del analizador.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import structlog

from umbral.config import get_settings

logger = structlog.get_logger()


@dataclass
class LLMResponse:
    """Respuesta normalizada de cualquier LLM."""
    text: str
    model: str
    provider: str
    tokens_used: Optional[int] = None


class BaseLLMProvider(ABC):
    """Clase base para proveedores de LLM."""
    
    provider_name: str = "base"
    
    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """
        Genera una respuesta del LLM.
        
        Args:
            system_prompt: Instrucciones del sistema
            user_prompt: Prompt del usuario
            temperature: Temperatura de generación (0.0-1.0)
            max_tokens: Máximo de tokens a generar
            
        Returns:
            LLMResponse con el texto generado
        """
        pass


class GeminiProvider(BaseLLMProvider):
    """Proveedor de Google Gemini."""
    
    provider_name = "gemini"
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        from google import genai
        
        settings = get_settings()
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY no configurada")
        
        self.client = genai.Client(api_key=self.api_key)
        logger.info("GeminiProvider inicializado", model=self.model)
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        from google.genai import types
        
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=[system_prompt, user_prompt],
            config=types.GenerateContentConfig(
                temperature=temperature,
                top_p=0.8,
                max_output_tokens=max_tokens,
            ),
        )
        
        return LLMResponse(
            text=response.text.strip(),
            model=self.model,
            provider=self.provider_name,
        )


class GroqProvider(BaseLLMProvider):
    """
    Proveedor de Groq (LPU inference).
    
    Modelos disponibles:
    - llama-3.1-8b-instant: Rápido y económico (560 t/s, $0.05/$0.08 per 1M)
    - llama-3.3-70b-versatile: Más capaz (280 t/s, $0.59/$0.79 per 1M)
    
    Docs: https://console.groq.com/docs/models
    """
    
    provider_name = "groq"
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        from groq import AsyncGroq
        
        settings = get_settings()
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        
        if not self.api_key:
            raise ValueError("GROQ_API_KEY no configurada")
        
        self.client = AsyncGroq(api_key=self.api_key)
        logger.info("GroqProvider inicializado", model=self.model)
    
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        text = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else None
        
        return LLMResponse(
            text=text.strip(),
            model=self.model,
            provider=self.provider_name,
            tokens_used=tokens,
        )


def get_llm_provider(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseLLMProvider:
    """
    Factory para obtener el proveedor de LLM configurado.
    
    Args:
        provider: 'gemini' o 'groq' (default: settings.llm_provider)
        api_key: API key (default: del settings según provider)
        model: Modelo a usar (default: del settings según provider)
        
    Returns:
        Instancia del proveedor configurado
    """
    settings = get_settings()
    provider = provider or settings.llm_provider
    
    if provider.lower() == "groq":
        return GroqProvider(api_key=api_key, model=model)
    elif provider.lower() == "gemini":
        return GeminiProvider(api_key=api_key, model=model)
    else:
        raise ValueError(f"Proveedor LLM no soportado: {provider}. Usar 'gemini' o 'groq'")


# Modelos disponibles por proveedor (para referencia)
AVAILABLE_MODELS = {
    "gemini": [
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    ],
    "groq": [
        "llama-3.1-8b-instant",      # Rápido, económico
        "llama-3.3-70b-versatile",   # Más capaz
        "llama-4-scout-17b-16e-instruct",  # Preview
    ],
}
