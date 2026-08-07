"""Integration (P1): embeddings over real Postgres."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from tests.integration.criteria.conftest import (
    build_criteria_service,
    seed_silver_listings,
)

from umbral.application.criteria.contracts import RecomputeScope
from umbral.infrastructure.db.models.criteria import (
    ListingEmbedding as EmbeddingModel,
)


class _Vectorizer:
    def embed(self, projection: Any) -> tuple[float, ...]:
        assert isinstance(projection, dict)
        assert "description_text" in projection
        assert "url" not in projection
        return (0.1,) * 1536


def test_embeddings_index_only_the_permitted_projection(criteria_backend: Any) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=2)
    service = build_criteria_service(
        factory,
        embeddings_enabled=True,
        embedding_model=_Vectorizer(),
    )
    summary = service.process_embeddings(
        RecomputeScope("full", None), correlation_id=uuid4()
    )
    assert summary == {"enabled": True, "published": 2}
    with factory() as session:
        rows = list(session.execute(select(EmbeddingModel)).scalars())
    assert len(rows) == 2
    assert all(row.state == "active" for row in rows)
    assert all(row.extraction_version_id is not None for row in rows)


def test_embeddings_disabled_by_default(criteria_backend: Any) -> None:
    factory = criteria_backend
    seed_silver_listings(factory, count=1)
    service = build_criteria_service(factory, embeddings_enabled=False)
    summary = service.process_embeddings(
        RecomputeScope("full", None), correlation_id=uuid4()
    )
    assert summary == {"enabled": False, "published": 0}
