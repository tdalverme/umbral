"""Tipos del scoring explicable."""

from pydantic import BaseModel, Field


class CriterionScore(BaseModel):
    name: str
    score: int = Field(ge=0, le=100)
    weight: int = Field(ge=0, le=100)
    reason: str


class ScoringResult(BaseModel):
    final_score: int = Field(ge=0, le=100)
    band: str
    summary: str
    criteria: list[CriterionScore] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    eligible: bool = True

    @property
    def normalized_score(self) -> float:
        return self.final_score / 100.0

    def to_personalized_analysis(self) -> dict:
        positives = [c.reason for c in self.criteria if c.score >= 70][:3]
        return {
            "why_match": self.summary,
            "warnings": "\n".join(self.gaps[:3]),
            "conclusion": "Vale la pena revisarla." if self.final_score >= 75 else "Puede servir, pero revisaria los puntos flojos.",
            "match_points": positives,
            "criteria": [c.model_dump() for c in self.criteria],
        }
