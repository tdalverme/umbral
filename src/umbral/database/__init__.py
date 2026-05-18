"""
Módulo de base de datos.

Provee acceso a Supabase y operaciones CRUD.
"""

from umbral.database.supabase_client import get_supabase_client, SupabaseClient
from umbral.database.repositories import (
    RawListingRepository,
    AnalyzedListingRepository,
    UserRepository,
    FeedbackRepository,
    NotificationRepository,
    UserListingMatchRepository,
    IngestionEventRepository,
    UrbanSignalRepository,
)

__all__ = [
    "get_supabase_client",
    "SupabaseClient",
    "RawListingRepository",
    "AnalyzedListingRepository",
    "UserRepository",
    "FeedbackRepository",
    "NotificationRepository",
    "UserListingMatchRepository",
    "IngestionEventRepository",
    "UrbanSignalRepository",
]
