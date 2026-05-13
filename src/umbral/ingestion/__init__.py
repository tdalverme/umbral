"""Pipeline de ingestion de publicaciones."""

from umbral.ingestion.models import NormalizedListingCandidate
from umbral.ingestion.service import IngestionService

__all__ = ["IngestionService", "NormalizedListingCandidate"]
