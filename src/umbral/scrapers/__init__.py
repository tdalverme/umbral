"""
Módulo de scrapers.

Provee scrapers para diferentes portales inmobiliarios.
"""

from umbral.scrapers.base import BaseScraper, ScraperResult
from umbral.scrapers.mercadolibre import MercadoLibreScraper

__all__ = [
    "BaseScraper",
    "ScraperResult",
    "MercadoLibreScraper",
]
