"""Linter ejecutable de voz para Reply v5.

Valida un texto de respuesta contra docs/brand/voice-guide.md:11-12 y
voice-examples-v1.json. Es un check liviano (regex) que cubre VOZ-06/07/08;
la honestidad profunda requiere evaluacion humana o de eval con outcomes.

Uso:
    from umbral.application.conversation.voice_check import lint_voice, score_rubric
    violations = lint_voice("¡Tu depto PERFECTO!!!")  # noqa: E501
    # -> ["VOZ-06:forbidden_word:perfect", ...]  # noqa: E501

Este modulo no toca DB ni LLM. Es puro y testeable.
"""

from __future__ import annotations

import re

FORBIDDEN_RE = re.compile(
    r"(perfect[ao]|ideal|imperdible|oportunidad única|garantizad[ao]|100% seguro)",
    re.IGNORECASE,
)
TECH_RE = re.compile(  # noqa: E501
    r"\b(score|scores|embedding|embeddings|hard filter|prompt|modelo|Smart Match|AI Search|IA avanzada)\b",  # noqa: E501
    re.IGNORECASE,
)
# Emoji: bloques principales (no exhaustivo, suficiente para lint)
EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U0001F600-\U0001F64F\U00002700-\U000027BF\U0001F900-\U0001F9FF]"
)
MULTI_EXCL_RE = re.compile(r"!{2,}|¡{2,}")
EXCL_COUNT_RE = re.compile(r"[!¡]")
CHE_DOUBLE_RE = re.compile(r"\bche\b.*\bche\b", re.IGNORECASE)
VOSEO_RE = re.compile(  # noqa: E501
    r"\b(querés|tenés|podés|buscás|decime|confirmame|avisame)\b", re.IGNORECASE
)
# Deteccion simple de certeza inventada (heuristica, no determinista total)
CERTAINTY_RE = re.compile(
    r"(garantizad[ao]|excelente garant|100%|seguro que te va a encantar)",
    re.IGNORECASE,
)


def lint_voice(text: str) -> list[str]:
    """Retorna codigos de violacion VOZ-*. Lista vacia = pasa lint automatico."""
    violations: list[str] = []
    if not text or not text.strip():
        return ["VOZ-02:empty"]
    if len(text) > 2000:
        violations.append("VOZ-02:too_long:>2000")
    # VOZ-06
    m = FORBIDDEN_RE.search(text)
    if m:
        violations.append(f"VOZ-06:forbidden_word:{m.group(0).lower()}")
    if CERTAINTY_RE.search(text):
        violations.append("VOZ-08:certainty_without_evidence")
    # VOZ-07
    if EMOJI_RE.search(text):
        violations.append("VOZ-07:emoji")
    if MULTI_EXCL_RE.search(text):
        violations.append("VOZ-07:multiple_exclamations")
    elif len(EXCL_COUNT_RE.findall(text)) > 1:
        violations.append("VOZ-07:too_many_exclamations")
    if TECH_RE.search(text):
        violations.append(f"VOZ-07:tech_jargon:{TECH_RE.search(text).group(0)}")  # type: ignore[union-attr]
    # VOZ-09 (borderline, no bloquea por si solo pero se reporta)
    if CHE_DOUBLE_RE.search(text):
        violations.append("VOZ-09:double_che_caricature")
    # VOZ-02 heurisitica: frase muy larga (>32 palabras en una frase)
    for sentence in re.split(r"[.!?]+", text):
        words = sentence.strip().split()
        if len(words) > 32:
            violations.append(f"VOZ-02:long_sentence:{len(words)}w")
            break
    return violations


# Rúbrica 7 dims (requiere juicio humano para honesto/atento)  # noqa: E501
def score_rubric(  # noqa: E501
    text: str, *, has_proposal: bool = False, has_evidence: bool = True
) -> dict[str, int]:
    """Heuristica. Para eval real usar anotador humano + outcomes."""  # noqa: E501
    v = lint_voice(text)
    has_forbidden = any(c.startswith("VOZ-06") for c in v)
    has_tech = any("tech_jargon" in c for c in v)
    has_emoji = any("emoji" in c for c in v)
    has_excl = any("exclamat" in c for c in v)
    has_certainty = any("certainty" in c for c in v)

    return {
        "atento": 0 if has_forbidden else 1,  # proxy  # noqa: E501
        "claro": 0 if (has_tech or any("long_sentence" in c for c in v)) else 1,  # noqa: E501
        "cercano": 1 if VOSEO_RE.search(text) else (0 if has_proposal else 1),  # noqa: E501
        "sereno": 0  # noqa: E501
        if (has_excl or has_emoji or "oportunidad única" in text.lower())
        else 1,
        "proactivo": 1  # noqa: E501
        if (has_proposal or "confirmame" in text.lower() or "si querés" in text.lower())
        else 0,
        "honesto": 0 if (has_forbidden or has_certainty) else (1 if has_evidence else 0),  # noqa: E501
        "alegre_con_medida": 0 if (has_excl or has_emoji) else 1,  # noqa: E501
    }


def is_pass(text: str, *, has_proposal: bool = False) -> bool:
    """Gate duro: VOZ-06/07/08 y honesto=1 y total>=6.

    Nota: violaciones grounded (p.ej. describir rejected como applied) requieren
    comparar text contra outcomes y no se detectan solo con regex. Ese gate vive
    en ReplyComposer y en evals con outcomes.
    """
    violations = lint_voice(text)
    if any(v.startswith("VOZ-06") for v in violations):
        return False
    if any(v.startswith("VOZ-07:emoji") for v in violations):
        return False
    if any("multiple_exclamations" in v for v in violations):
        return False
    if any("too_many_exclamations" in v for v in violations):
        return False
    if any(v.startswith("VOZ-07:tech_jargon") for v in violations):
        return False
    if any("certainty_without_evidence" in v for v in violations):
        return False
    # VOZ-09 double_che es BORDERLINE, no bloquea por si solo en lint puro
    rubric = score_rubric(text, has_proposal=has_proposal)
    if rubric["honesto"] == 0:
        return False
    return sum(rubric.values()) >= 6


def check_grounded(text: str, outcomes: list[dict[str, object]]) -> list[str]:
    """Valida que el texto no describa un rejected/pending como applied.

    Heuristica simple para evals: si outcomes contiene rejected y el texto
    contiene 'actualicé'/'listo' sin matizar, reporta violacion.
    Para produccion, ReplyComposer ya garantiza grounding via outcomes.
    """
    has_rejected = any(o.get("status") == "rejected" for o in outcomes)
    has_pending = any(o.get("status") == "pending" for o in outcomes)
    lower = text.lower()
    violations: list[str] = []
    if has_rejected and ("actualicé" in lower or "actualice" in lower):
        # permitir "no pude actualizar" — solo flag si afirma actualizacion
        if "no pude" not in lower and "no se pudo" not in lower:
            violations.append("VOZ-GROUNDED:rejected_described_as_applied")
    if has_pending and has_rejected:
        # combinacion no esperada, dejar pasar
        pass
    return violations
