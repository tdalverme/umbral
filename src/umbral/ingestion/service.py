"""Servicio de ingestion: normaliza, deduplica y aplica quality gate."""

from __future__ import annotations

import structlog

from umbral.database import IngestionEventRepository, RawListingRepository
from umbral.ingestion.models import NormalizedListingCandidate
from umbral.quality import evaluate_listing_quality

logger = structlog.get_logger()


class IngestionService:
    """Entrada unica para persistir candidatos scrapeados."""

    def __init__(
        self,
        raw_repo: RawListingRepository | None = None,
        event_repo: IngestionEventRepository | None = None,
    ):
        self.raw_repo = raw_repo or RawListingRepository()
        self.event_repo = event_repo or IngestionEventRepository()

    def ingest_candidate(self, candidate: NormalizedListingCandidate) -> dict:
        raw_listing = candidate.to_raw_listing()
        duplicate = self.raw_repo.exists_by_hash(raw_listing.hash_id)
        quality = evaluate_listing_quality(raw_listing, duplicate=duplicate)

        if not quality.accepted:
            self.event_repo.create(
                source=raw_listing.source,
                external_id=raw_listing.external_id,
                url=raw_listing.url,
                status="rejected",
                quality_score=quality.score,
                reason=quality.reason,
                tags=quality.tags,
            )
            logger.info(
                "Listing rechazado por quality gate",
                external_id=raw_listing.external_id,
                score=quality.score,
                reason=quality.reason,
            )
            return {"accepted": False, "quality": quality.model_dump(), "listing": None}

        saved = self.raw_repo.upsert(raw_listing)
        self.event_repo.create(
            source=raw_listing.source,
            external_id=raw_listing.external_id,
            url=raw_listing.url,
            status="accepted",
            raw_listing_id=saved.get("id"),
            quality_score=quality.score,
            reason=quality.reason,
            tags=quality.tags,
        )
        return {"accepted": True, "quality": quality.model_dump(), "listing": saved}
