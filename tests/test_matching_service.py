from dataclasses import dataclass

from umbral.matching.engine import MatchingService
from umbral.models.user import HardFilters, SoftPreferences, UserPreferences


def _preferences():
    return UserPreferences(
        hard_filters=HardFilters(
            operation_type="alquiler",
            max_price_usd=900,
            neighborhoods=["Palermo"],
            min_rooms=2,
            max_rooms=3,
            requires_balcony=True,
        ),
        soft_preferences=SoftPreferences(
            ideal_description="Quiero luz, silencio y buen lugar para trabajar desde casa.",
            weight_luminosity=0.9,
            weight_quietness=0.8,
            weight_wfh_suitability=0.9,
        ),
    )


def _candidate():
    return {
        "id": "analyzed-1",
        "raw_listing_id": "raw-1",
        "raw_listings": {
            "id": "raw-1",
            "title": "Departamento luminoso con balcon",
            "description": "Contrafrente luminoso, balcon y ambiente tranquilo.",
            "url": "https://example.test/listing",
            "price": 780,
            "currency": "USD",
            "features": {"has_balcony": True},
        },
        "operation_type": "alquiler",
        "price_usd": 780,
        "price_original": 780,
        "currency_original": "USD",
        "price_per_m2_usd": 18,
        "quality_score": 88,
        "neighborhood": "Palermo",
        "rooms": 2,
        "features": {"has_balcony": True},
        "raw_features": {"has_balcony": True, "is_pet_friendly": True},
        "scores": {
            "quietness": 0.8,
            "luminosity": 0.9,
            "connectivity": 0.8,
            "wfh_suitability": 0.9,
            "modernity": 0.7,
            "green_spaces": 0.6,
        },
        "urban_signals": {
            "noise_risk": 0.2,
            "walkability": 0.85,
            "transit_access": 0.8,
            "green_access": 0.6,
            "nightlife_intensity": 0.2,
            "daily_convenience": 0.9,
            "cafe_lifestyle": 0.6,
            "commercial_intensity": 0.5,
            "residential_calm": 0.75,
            "confidence": 0.9,
        },
    }


class FakeListingRepo:
    def find_candidates_for_user(self, preferences, limit=300):
        return [_candidate()]


class FakeNotificationRepo:
    def was_sent(self, user_id, analyzed_listing_id):
        return False


class FakeFeedbackRepo:
    def get_user_feedback(self, user_id):
        return []


class FakeMatchRepo:
    def __init__(self):
        self.rows = []

    def upsert_many(self, rows):
        self.rows.extend(rows)


@dataclass
class FakePersonalizedAnalysis:
    why_match: str
    warnings: str
    conclusion: str


class FakePersonalizedAnalyzer:
    def __init__(self):
        self.calls = []

    async def generate(self, preferences, listing_data, similarity_score):
        self.calls.append((preferences, listing_data, similarity_score))
        return FakePersonalizedAnalysis(
            why_match="Tiene balcon, buena luz y encaja con tu idea de trabajar tranquilo.",
            warnings="El precio queda dentro de presupuesto, pero no sobra tanto margen.",
            conclusion="Es una candidata real para mirar con calma.",
        )


async def test_matching_service_uses_personalized_analyzer_for_notifications():
    analyzer = FakePersonalizedAnalyzer()
    service = MatchingService(
        listing_repo=FakeListingRepo(),
        notification_repo=FakeNotificationRepo(),
        match_repo=FakeMatchRepo(),
        feedback_repo=FakeFeedbackRepo(),
        personalized_match_analyzer=analyzer,
    )

    matches = await service.find_matches_for_user(
        user_id="user-1",
        preferences=_preferences(),
        limit=1,
        min_score=75,
    )

    assert len(matches) == 1
    assert analyzer.calls
    assert matches[0].personalized_analysis.why_match.startswith("Tiene balcon")
    assert matches[0].personalized_analysis.why_match != matches[0].scoring.summary
