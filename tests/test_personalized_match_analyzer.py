from umbral.analysis.llm_providers import LLMResponse
from umbral.analysis.personalized_match_analyzer import PersonalizedMatchAnalyzer
from umbral.models.user import HardFilters, SoftPreferences, UserPreferences


class CapturingProvider:
    def __init__(self):
        self.user_prompt = ""

    async def generate(self, system_prompt, user_prompt, temperature=0.2, max_tokens=4096):
        self.user_prompt = user_prompt
        return LLMResponse(
            text='{"why_match":"Esta en Palermo y tiene balcon, dos puntos que pediste.","warnings":"Ojo que el precio queda cerca del limite.","conclusion":"Vale mirarla si aceptas ese trade-off."}',
            model="fake",
            provider="fake",
        )


def _preferences():
    return UserPreferences(
        hard_filters=HardFilters(
            max_price_usd=900,
            neighborhoods=["Palermo"],
            min_rooms=2,
            max_rooms=3,
            requires_balcony=True,
        ),
        soft_preferences=SoftPreferences(
            ideal_description="Quiero luz y silencio para trabajar desde casa.",
        ),
    )


async def test_personalized_prompt_includes_scoring_context_and_generic_warning():
    provider = CapturingProvider()
    analyzer = PersonalizedMatchAnalyzer(provider=provider)

    await analyzer.generate(
        _preferences(),
        {
            "title": "Departamento luminoso",
            "neighborhood": "Palermo",
            "price": 870,
            "currency": "USD",
            "rooms": 2,
            "features": {"has_balcony": True},
            "description": "Contrafrente con balcon y buena luz.",
            "criteria": [
                {"name": "Location fit", "score": 90, "reason": "Esta en Palermo."},
                {"name": "Price/budget fit", "score": 68, "reason": "Precio cerca del limite."},
            ],
            "gaps": ["Expensas no confirmadas."],
        },
        similarity_score=0.82,
    )

    assert "No uses frases genericas" in provider.user_prompt
    assert "Location fit: 90" in provider.user_prompt
    assert "Precio cerca del limite" in provider.user_prompt
    assert "Expensas no confirmadas" in provider.user_prompt
