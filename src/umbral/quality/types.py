"""Tipos para el quality gate de publicaciones."""

from pydantic import BaseModel, Field


class QualityResult(BaseModel):
    """Resultado explicable del quality gate."""

    accepted: bool
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @property
    def reason(self) -> str:
        parts = self.reasons + self.penalties
        return "; ".join(parts) if parts else "Sin evaluacion"
