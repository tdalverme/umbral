"""US6 (P1): embedding generation from the permitted projection only."""

from __future__ import annotations

from uuid import uuid4

from tests.support.criteria import CriteriaTestContext

from umbral.application.criteria.contracts import RecomputeScope


class _Vectorizer:
    def embed(self, projection: object) -> tuple[float, ...]:
        assert isinstance(projection, dict)
        assert "description_text" in projection or "location_text" in projection
        assert "url" not in projection
        return (0.1,) * 1536


def test_embeddings_disabled_by_default_has_no_effect() -> None:
    context = CriteriaTestContext()
    context.seed_concepts()
    context.add_listing(description_text="con balcon")
    summary = context.service.process_embeddings(
        RecomputeScope("full", None), correlation_id=uuid4()
    )
    assert summary == {"enabled": False, "published": 0}


def test_embeddings_generate_from_permitted_projection_when_enabled() -> None:
    context = CriteriaTestContext(
        embeddings_enabled=True, embedding_model=_Vectorizer()
    )
    context.seed_concepts()
    context.add_listing(description_text="con balcon en Caballito")
    summary = context.service.process_embeddings(
        RecomputeScope("full", None), correlation_id=uuid4()
    )
    assert summary == {"enabled": True, "published": 1}
    version = context.extraction_versions.find("embedding", "embeddings-v1", "v1")
    assert version is not None
    assert version.payload["model"] == "embeddings-v1"
