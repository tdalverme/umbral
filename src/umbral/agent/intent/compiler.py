"""Intent compilation over the model gateway (UM-H4-017, R-01/R-02)."""

from __future__ import annotations

from collections.abc import Mapping

from umbral.agent.intent.contracts import (
    IntentCompilation,
    IntentCompilationFailed,
    IntentContract,
    IntentContradiction,
    IntentParameter,
    IntentUnclassified,
)
from umbral.application.agent.ports import ModelGateway

_INTENT_EXAMPLES: Mapping[str, tuple[str, ...]] = {
    "consulta": (
        "que criterios tengo?",
        "por que me recomendaste este depto?",
        "mostrame los matches de mi radar",
        "quiero empezar a buscar un depto en Palermo",
        "quiero ver deptos en Palermo",
        "empecemos: mostrame opciones",
    ),
    "refinamiento": (
        "aumenta el presupuesto",
        "baja el presupuesto a la mitad",
        "quiero vivir en una zona linda",
        "cambia el radio de busqueda",
        "no me vuelvas a mostrar cosas de ese barrio",
        "quiero un depto luminoso",
        "prefiero con balcon",
        "quiero una cocina separada",
        "no me gustan los deptos oscuros",
    ),
    "comparacion": (
        "compara estos dos deptos que guarde",
        "cual es mejor, el de Cabrera o el de Gorriti?",
        "compara los dos que tengo en la lista",
    ),
    "feedback": (
        "este depto no me gusta",
        "me encanto este depto",
        "guarda este, me interesa",
    ),
    "fuera_de_alcance": (
        "contame un chiste de programacion",
        "borra mi cuenta y todos mis datos",
        "crea un radar nuevo desde cero",
        "hace vos el ranking y decime cual es el mejor de todos",
        "quien gano el mundial?",
    ),
}

_CANONICAL_KEYS: Mapping[str, str] = {
    "budget": "budget",
    "presupuesto": "budget",
    "precio": "budget",
    "plata": "budget",
    "dinero": "budget",
    "zona": "zona",
    "barrio": "zona",
    "ubicacion": "zona",
    "lugar": "zona",
    "hard_filters": "hard_filters",
    "hardfilters": "hard_filters",
    "filtros": "hard_filters",
    "filtros_duros": "hard_filters",
    "radio": "radio",
    "radio_de_busqueda": "radio",
    "ambientes": "ambientes",
    "habitaciones": "ambientes",
    "cuartos": "ambientes",
    "rooms": "ambientes",
    "superficie": "superficie",
    "metros": "superficie",
    "metros_cuadrados": "superficie",
    "m2": "superficie",
    "preferencia": "preferencia",
    "preferencias": "preferencia",
}


def _canonical_key(key: str) -> str:
    return _CANONICAL_KEYS.get(key.strip().lower(), key.strip().lower())


class IntentCompiler:
    """Classifies a message into exactly one intent and extracts parameters.

    The model only fills the ``output`` section of intent-schema-v3; the
    allowed-tools policy comes from the machine-checkable contract, not from
    the model (R-02).
    """

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        contract: IntentContract,
        prompt_version: str,
        model_version: str,
    ) -> None:
        self.gateway = gateway
        self.contract = contract
        self.prompt_version = prompt_version
        self.model_version = model_version

    def compile(
        self,
        *,
        message_text: str,
        clarification_context: Mapping[str, object] | None = None,
    ) -> IntentCompilation:
        messages = [
            {"role": "user", "content": message_text},
        ]
        if clarification_context:
            pending = clarification_context.get("pending_params")
            pending_text = (
                ", ".join(str(item) for item in pending)
                if isinstance(pending, list)
                else ""
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "El usuario esta respondiendo la aclaracion sobre: "
                        f"{pending_text}. Integra la respuesta a esos parametros."
                    ),
                }
            )
        prompt_schema = dict(self.contract.output_schema)
        prompt_schema["_intents"] = [
            {
                "name": declaration.name,
                "description": declaration.description,
                "examples": _INTENT_EXAMPLES.get(declaration.name, []),
            }
            for declaration in self.contract.intents
        ]
        prompt_schema["parameters"] = {
            "kind": "list",
            "item": {
                "key": "string",
                "value": "string",
                "confidence": "number",
            },
            "description": (
                "Parametros del mensaje con claves canonicas "
                "(budget, zona, ambientes, superficie, hard_filters, radio, "
                "preferencia u otra relevante del dominio), value en texto "
                "plano y confidence entre 0 y 1. Ejemplos de extraccion: "
                "'Subi el presupuesto a 900' -> [budget=900, confianza alta]; "
                "'Quiero 2 ambientes en Palermo' -> [ambientes=2, zona=Palermo]; "
                "'Quiero un depto luminoso' -> [preferencia=luminoso, "
                "confianza alta]; 'Prefiero con balcon' -> "
                "[preferencia=con balcon, confianza alta]."
            ),
        }
        prompt_schema["high_impact_missing"] = {
            "kind": "list",
            "item": "string",
            "description": (
                "Solo claves canonicas de alto impacto "
                "(budget, zona, hard_filters, radio) que falten y sean "
                "necesarias para el cambio pedido; vacio en consultas de "
                "solo lectura. Nunca claves inventadas. Para refinamiento: "
                "'Aumenta el presupuesto' (sin valor nuevo) -> [budget]; "
                "'Quiero vivir en una zona linda' (zona vaga) -> [zona]; "
                "'Subi el presupuesto a 900' (valor concreto) -> []."
            ),
        }
        result = self.gateway.generate_structured(
            messages=tuple(messages),
            schema=prompt_schema,
            schema_version=self.contract.schema_version,
            prompt_version=self.prompt_version,
            model_version=self.model_version,
        )
        if result.status != "success" or result.content is None:
            raise IntentCompilationFailed()
        raw = result.content
        intent = raw.get("intent")
        if not isinstance(intent, str) or intent not in self.contract.known_intents():
            raise IntentUnclassified()
        raw_parameters = raw.get("parameters")
        raw_missing = raw.get("high_impact_missing")
        raw_contradictions = raw.get("contradictions")
        parameters = tuple(
            IntentParameter(
                key=_canonical_key(_string(item, "key")),
                value=_string(item, "value"),
                confidence=_number(item.get("confidence"), 0.0),
            )
            for item in (raw_parameters if isinstance(raw_parameters, list) else [])
            if isinstance(item, Mapping) and "key" in item and "value" in item
        )
        missing = tuple(
            _canonical_key(item)
            for item in (raw_missing if isinstance(raw_missing, list) else [])
            if isinstance(item, str)
        )
        contradictions = tuple(
            IntentContradiction(
                key=_string(item, "key"),
                current_value=_string(item, "current_value"),
                requested=_string(item, "requested"),
            )
            for item in (
                raw_contradictions if isinstance(raw_contradictions, list) else []
            )
            if isinstance(item, Mapping) and "key" in item
        )
        return IntentCompilation(
            intent=intent,
            parameters=parameters,
            high_impact_missing=missing,
            contradictions=contradictions,
            allowed_tools=self.contract.allowed_tools_for(intent),
        )


def _string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    return value if isinstance(value, str) else str(value or "")


def _number(value: object, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default
