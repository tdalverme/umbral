from umbral.models import ListingFeatures, RawListing
from umbral.quality import evaluate_listing_quality


def _listing(**overrides):
    data = {
        "external_id": "ml-1",
        "url": "https://example.com/listing/1",
        "source": "mercadolibre",
        "title": "Departamento luminoso de 2 ambientes en Palermo",
        "description": "Departamento muy luminoso, con balcon, buena distribucion, cocina integrada y excelente ubicacion cerca de transporte y comercios.",
        "price": "700",
        "currency": "USD",
        "location": "Palermo, CABA",
        "neighborhood": "Palermo",
        "rooms": "2",
        "images": ["https://example.com/photo.jpg"],
        "features": ListingFeatures(has_balcony=True, has_elevator=True),
    }
    data.update(overrides)
    return RawListing(**data)


def test_quality_gate_accepts_complete_listing():
    result = evaluate_listing_quality(_listing())

    assert result.accepted is True
    assert result.score >= 70
    assert result.reasons


def test_quality_gate_rejects_missing_url_price_and_neighborhood():
    result = evaluate_listing_quality(
        _listing(url="", price="", neighborhood="", description="Muy corto")
    )

    assert result.accepted is False
    assert "missing_url" in result.tags
    assert "missing_price" in result.tags
    assert "missing_neighborhood" in result.tags
    assert result.penalties


def test_quality_gate_rejects_duplicates_with_reason():
    result = evaluate_listing_quality(_listing(), duplicate=True)

    assert result.accepted is False
    assert result.score == 0
    assert "duplicate" in result.tags
