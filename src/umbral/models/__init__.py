"""
Modelos de datos del sistema.

Implementa arquitectura Medallion:
- Bronze: RawListing (datos crudos)
- Gold: AnalyzedListing (datos procesados)
"""

from umbral.models.raw_listing import RawListing, ListingFeatures
from umbral.models.analyzed_listing import (
    AnalyzedListing,
    InferredFeatures,
    PropertyScores,
)
from umbral.models.user import User, UserPreferences, HardFilters

__all__ = [
    # Bronze
    "RawListing",
    "ListingFeatures",
    # Gold
    "AnalyzedListing",
    "InferredFeatures",
    "PropertyScores",
    # User
    "User",
    "UserPreferences",
    "HardFilters",
]
