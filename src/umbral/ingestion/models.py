"""Modelos de ingestion normalizados."""

from pydantic import BaseModel, Field

from umbral.models import ListingFeatures, RawListing


class NormalizedListingCandidate(BaseModel):
    """Contrato comun para candidatos que salen de cualquier scraper."""

    external_id: str
    url: str
    source: str
    title: str
    description: str
    price: str
    currency: str
    location: str
    neighborhood: str
    region: str = "CABA"
    city: str = "Buenos Aires"
    rooms: str
    bathrooms: str = "1"
    size_total: str = ""
    size_covered: str = ""
    age: str | None = None
    disposition: str | None = None
    orientation: str | None = None
    maintenance_fee: str | None = None
    operation_type: str = "alquiler"
    images: list[str] = Field(default_factory=list)
    coordinates: dict | None = None
    parking_spaces: int | None = None
    features: ListingFeatures = Field(default_factory=ListingFeatures)

    @classmethod
    def from_raw_listing(cls, listing: RawListing) -> "NormalizedListingCandidate":
        return cls(**listing.model_dump(exclude={"embedding_vector", "scraped_at", "hash_id"}))

    def to_raw_listing(self) -> RawListing:
        return RawListing(**self.model_dump())
