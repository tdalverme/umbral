"""Deterministic clarification policy for high-impact parameters (R-03)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

_CONTRADICTION_KEY = "contradiccion"

_QUESTIONS: Mapping[str, str] = {
    "budget": "¿Cuál es tu presupuesto máximo para esta búsqueda?",
    "zona": "¿En qué zona querés buscar?",
    "hard_filters": "¿Qué valor querés fijar para ese filtro?",
    "radio": "¿Qué radio de búsqueda necesitás?",
    "contradiccion": (
        "El cambio que pedís contradice tu radar actual. ¿Cómo preferís dejarlo?"
    ),
}


@dataclass(frozen=True, slots=True)
class ClarificationPlan:
    """The bounded clarification interaction for the current turn."""

    pending_params: tuple[str, ...]
    rounds: int
    max_rounds: int

    def exceeded(self) -> bool:
        """True when the clarification budget is exhausted (FR-008)."""
        return self.rounds >= self.max_rounds


def decide(
    *,
    intent: str,
    parameters: Sequence[object],
    high_impact_missing: Sequence[str],
    contradictions: Sequence[object],
    high_impact_keys: Sequence[str],
    min_confidence: float,
    rounds: int,
    max_rounds: int,
) -> ClarificationPlan | None:
    """Return a clarification plan when high-impact parameters are ambiguous,
    missing or contradictory; None otherwise. 0 guessing (FR-006/FR-007)."""
    if intent == "fuera_de_alcance":
        return None
    keys = frozenset(high_impact_keys)
    pending: list[str] = []
    for item in contradictions:
        if isinstance(item, Mapping) and item.get("key"):
            pending.append(_CONTRADICTION_KEY)
            break
    for item in parameters:
        key = item.get("key") if isinstance(item, Mapping) else None
        confidence = item.get("confidence") if isinstance(item, Mapping) else None
        if (
            isinstance(key, str)
            and key in keys
            and isinstance(confidence, (int, float))
            and confidence < min_confidence
        ):
            if key not in pending:
                pending.append(key)
    for key in high_impact_missing:
        if isinstance(key, str) and key not in pending:
            pending.append(key)
    if not pending:
        return None
    return ClarificationPlan(
        pending_params=tuple(pending), rounds=rounds, max_rounds=max_rounds
    )


def render_question(plan: ClarificationPlan) -> str:
    """Render a deterministic, redacted question for the plan (0 LLM)."""
    if plan.exceeded():
        return (
            "No puedo aplicar ese cambio sin confirmar los datos que faltan. "
            "Revisá y ajustá los criterios directamente en tu radar."
        )
    if len(plan.pending_params) == 1:
        return _QUESTIONS.get(plan.pending_params[0], "¿Podés darme más detalle?")
    return (
        "Para aplicar ese cambio necesito confirmar: "
        + ", ".join(plan.pending_params)
        + "."
    )
