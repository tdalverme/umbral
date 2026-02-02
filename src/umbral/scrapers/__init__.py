"""
Módulo de scrapers.

Provee scrapers para diferentes portales inmobiliarios.
"""

from umbral.scrapers.base import BaseScraper, ScraperResult
from umbral.scrapers.mercadolibre import MercadoLibreScraper
from umbral.scrapers.argenprop import ArgenPropScraper

__all__ = [
    "BaseScraper",
    "ScraperResult",
    "MercadoLibreScraper",
    "ArgenPropScraper",
]
