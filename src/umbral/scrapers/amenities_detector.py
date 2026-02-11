"""
Deteccion generica de amenities por texto libre.

Se usa como fallback cuando el portal no expone bien las
caracteristicas estructuradas, pero si aparecen en titulo/descripcion.
"""

import re
import unicodedata
from typing import Optional


class KeywordAmenitiesDetector:
    """Detector simple basado en keywords + negaciones cercanas."""

    FEATURE_PATTERNS: dict[str, list[str]] = {
        "is_furnished": [
            r"\bamoblad[oa]s?\b",
            r"\bamueblad[oa]s?\b",
            r"\bfull amoblad[oa]\b",
            r"\btotalmente amoblad[oa]\b",
            r"\bse entrega amoblad[oa]\b",
            r"\bincluye muebles\b",
            r"\bcon muebles\b",
        ],
        "is_pet_friendly": [r"\bpet friendly\b", r"\bacepta mascotas?\b", r"\bmascotas? permitidas?\b", r"\bapto mascotas?\b"],
        "has_security": [r"\bseguridad\b", r"\bvigilancia\b", r"\bporteri?a\b", r"\bportero\b", r"\bcamaras?\b", r"\balarma\b"],
        "has_elevator": [r"\bascensor(?:es)?\b", r"\belevador(?:es)?\b"],
        "has_gas": [r"\bgas natural\b", r"\bgas de red\b", r"\bcon gas\b"],
        "has_air_conditioning": [r"\baire acondicionado\b", r"\bsplit\b", r"\bfrio\/calor\b", r"\bfrio calor\b"],
        "has_heating": [r"\bcalefaccion\b", r"\bcalefactor(?:es)?\b", r"\bradiador(?:es)?\b", r"\blosa radiante\b", r"\bcaldera\b"],
        "has_laundry": [r"\blavadero\b", r"\blavanderia\b", r"\blaundry\b", r"\bespacio para lavarropas\b", r"\bconexion para lavarropas\b"],
        "has_sum": [r"\bsum\b", r"\bsalon de usos multiples\b", r"\bsalon de fiestas\b"],
        "has_bbq": [r"\bparrilla(?:s)?\b", r"\bquincho(?:s)?\b", r"\bbbq\b"],
        "has_pool": [r"\bpileta\b", r"\bpiscina\b", r"\bnatatorio\b", r"\bsolarium\b"],
        "has_gym": [r"\bgimnasio\b", r"\bgym\b", r"\bfitness\b"],
        "has_balcony": [r"\bbalcon(?:es)?\b"],
        "has_terrace": [r"\bterraza\b", r"\brooftop\b", r"\bazotea\b"],
        "has_garden": [
            r"\bjardin(?:es)?\b",
            r"\bcon jardin\b",
            r"\bjardin (?:propio|privado|interno|de invierno)\b",
            r"\bparque propio\b",
        ],
        "has_patio": [r"\bpatio\b", r"\bpatio de luz\b", r"\bpatio interno\b"],
    }

    PARKING_PATTERNS: list[str] = [
        r"\bcochera(?:s)?\b",
        r"\bgarage(?:s)?\b",
        r"\bgaraje(?:s)?\b",
        r"\bestacionamiento\b",
        r"\bparking\b",
    ]

    NEGATION_PATTERNS: list[str] = [
        r"\bno\b",
        r"\bsin\b",
        r"\bcarece\b",
        r"\bno tiene\b",
        r"\bno posee\b",
        r"\bno cuenta con\b",
        r"\bno incluye\b",
        r"\bprohibido\b",
        r"\bno se aceptan\b",
        r"\bno se permiten\b",
    ]

    FEATURE_EXCLUSION_PATTERNS: dict[str, list[str]] = {
        # Evitar falsos positivos de "muebles" estructurales y no amoblamiento.
        "is_furnished": [
            r"\bmuebles? de cocina\b",
            r"\bmueble bajo mesada\b",
            r"\balacena(?:s)?\b",
            r"\bplacard(?:es)?\b",
            r"\bmueble(?:s)? de bano\b",
        ],
        # Evitar tomar como jardin la cercania a parques/plazas del barrio.
        "has_garden": [
            r"\bcerca de\b",
            r"\ba metros de\b",
            r"\ba pasos de\b",
            r"\bfrente a\b",
            r"\bparque sarmiento\b",
            r"\bplaza\b",
            r"\bboulevard\b",
            r"\bentorno verde\b",
        ],
    }

    def _normalize(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text or "")
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        return re.sub(r"\s+", " ", ascii_text).strip().lower()

    def _split_sentences(self, text: str) -> list[str]:
        return [s.strip() for s in re.split(r"[.!?\n;:]+", text) if s.strip()]

    def _is_negated(self, sentence: str, keyword_pattern: str) -> bool:
        for match in re.finditer(keyword_pattern, sentence, flags=re.IGNORECASE):
            start = max(0, match.start() - 45)
            end = min(len(sentence), match.end() + 25)
            window = sentence[start:end]
            for neg_pattern in self.NEGATION_PATTERNS:
                if re.search(neg_pattern, window, flags=re.IGNORECASE):
                    return True
        return False

    def _is_excluded_context(self, feature: str, sentence: str) -> bool:
        exclusion_patterns = self.FEATURE_EXCLUSION_PATTERNS.get(feature, [])
        for pattern in exclusion_patterns:
            if re.search(pattern, sentence, flags=re.IGNORECASE):
                return True
        return False

    def detect_features(self, text: str) -> dict[str, bool]:
        normalized = self._normalize(text)
        sentences = self._split_sentences(normalized)

        results = {feature: False for feature in self.FEATURE_PATTERNS}
        for sentence in sentences:
            for feature, patterns in self.FEATURE_PATTERNS.items():
                if results[feature]:
                    continue
                for pattern in patterns:
                    if re.search(pattern, sentence, flags=re.IGNORECASE):
                        if not self._is_negated(sentence, pattern):
                            if self._is_excluded_context(feature, sentence):
                                continue
                            results[feature] = True
                            break
        return results

    def detect_features_with_evidence(self, text: str) -> dict[str, dict]:
        """
        Detecta amenities y devuelve evidencia del disparador.

        Returns:
            {
                "has_balcony": {
                    "value": True/False,
                    "matched_pattern": "...",
                    "matched_sentence": "..."
                },
                ...
            }
        """
        normalized = self._normalize(text)
        sentences = self._split_sentences(normalized)
        results: dict[str, dict] = {}

        for feature, patterns in self.FEATURE_PATTERNS.items():
            results[feature] = {
                "value": False,
                "matched_pattern": None,
                "matched_sentence": None,
            }
            for sentence in sentences:
                found = False
                for pattern in patterns:
                    if re.search(pattern, sentence, flags=re.IGNORECASE):
                        if self._is_negated(sentence, pattern):
                            found = True
                            break
                        if self._is_excluded_context(feature, sentence):
                            found = True
                            break
                        results[feature] = {
                            "value": True,
                            "matched_pattern": pattern,
                            "matched_sentence": sentence,
                        }
                        found = True
                        break
                if found and results[feature]["value"]:
                    break

        return results

    def detect_parking_spaces(self, text: str) -> Optional[int]:
        normalized = self._normalize(text)
        sentences = self._split_sentences(normalized)

        for sentence in sentences:
            count_match = re.search(
                r"\b(\d+)\s*(cochera(?:s)?|garage(?:s)?|garaje(?:s)?|espacios? de estacionamiento)\b",
                sentence,
                flags=re.IGNORECASE,
            )
            if count_match and not self._is_negated(sentence, count_match.group(2)):
                try:
                    return int(count_match.group(1))
                except ValueError:
                    pass

            for pattern in self.PARKING_PATTERNS:
                if re.search(pattern, sentence, flags=re.IGNORECASE):
                    if not self._is_negated(sentence, pattern):
                        return 1
        return None

    def detect_parking_with_evidence(self, text: str) -> dict[str, Optional[object]]:
        """Detecta parking y devuelve evidencia textual del match."""
        normalized = self._normalize(text)
        sentences = self._split_sentences(normalized)

        for sentence in sentences:
            count_match = re.search(
                r"\b(\d+)\s*(cochera(?:s)?|garage(?:s)?|garaje(?:s)?|espacios? de estacionamiento)\b",
                sentence,
                flags=re.IGNORECASE,
            )
            if count_match and not self._is_negated(sentence, count_match.group(2)):
                try:
                    return {
                        "value": int(count_match.group(1)),
                        "matched_pattern": count_match.re.pattern,
                        "matched_sentence": sentence,
                    }
                except ValueError:
                    pass

            for pattern in self.PARKING_PATTERNS:
                if re.search(pattern, sentence, flags=re.IGNORECASE):
                    if not self._is_negated(sentence, pattern):
                        return {
                            "value": 1,
                            "matched_pattern": pattern,
                            "matched_sentence": sentence,
                        }

        return {
            "value": None,
            "matched_pattern": None,
            "matched_sentence": None,
        }
