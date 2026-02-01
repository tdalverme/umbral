"""
Motor de matching.

Combina filtros hard y similitud semántica para encontrar
las propiedades más relevantes para cada usuario.
"""

from umbral.matching.engine import MatchingEngine, MatchResult

__all__ = [
    "MatchingEngine",
    "MatchResult",
]
