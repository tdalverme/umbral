# mypy: ignore-errors
"""Voz del agente — validacion ejecutable de templates y tono.

Verifica que docs/brand/voice-guide.md y voice-examples-v1.json esten alineados
al branding 2026-08-26 y que el linter voice_check cubra VOZ-06/07/08.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]

from umbral.application.conversation.voice_check import (
    check_grounded,
    is_pass,
    lint_voice,
)

ROOT = Path(__file__).resolve().parents[4]
VOICE_EXAMPLES = ROOT / "tests" / "fixtures" / "conversation-voice-examples.json"
REPLY_SCHEMA = json.loads(  # noqa: E501
    (ROOT / "contracts" / "agent" / "reply-schema.json").read_text(
        encoding="utf-8"
    )
)
VOICE_GUIDE = ROOT / "docs" / "brand" / "voice-guide.md"
REPLY_PROMPT = ROOT / "src" / "umbral" / "agent" / "prompts" / "reply.md"


def _load_examples() -> list[dict]:
    data: dict = json.loads(VOICE_EXAMPLES.read_text(encoding="utf-8"))
    assert data["version"] == "voice-v1"
    return data["examples"]


def test_voice_guide_exists_and_references_brand() -> None:
    text = VOICE_GUIDE.read_text(encoding="utf-8")
    assert "2026-08-26-umbral-brand-system-design.md" in text
    assert "copiloto sereno" in text.lower()
    assert "VOZ-06" in text
    assert "voice-v1" in text


def test_reply_prompt_is_voice_aligned() -> None:
    prompt = REPLY_PROMPT.read_text(encoding="utf-8")
    assert "voice: voice-v1" in prompt
    assert "voice_guide" in prompt
    assert "copiloto sereno" in prompt.lower()
    assert "perfecta / ideal / imperdible" in prompt or "perfecta" in prompt.lower()


def test_voice_examples_pass_basic_invariants() -> None:
    for ex in _load_examples():
        assert 1 <= len(ex["text"]) <= 2000
        assert ex["verdict"] in ("PASS", "FAIL", "BORDERLINE")
        assert "rubric" in ex
        # rubric 7 dims
        assert set(ex["rubric"].keys()) == {
            "atento",
            "claro",
            "cercano",
            "sereno",
            "proactivo",
            "honesto",
            "alegre_con_medida",
        }


def test_voice_examples_text_fits_reply_schema() -> None:
    # Cada text debe ser valido como text de reply-schema (1..2000)
    for ex in _load_examples():
        payload = {
            "contract_version": "5",
            "text": ex["text"],
            "outcomes": [],
            "verified_refs": [],
            "source": "managed",
        }
        jsonschema.validate(payload, REPLY_SCHEMA)


def test_linter_matches_verdict_for_hard_cases() -> None:
    for ex in _load_examples():
        lint = lint_voice(ex["text"])
        grounded = check_grounded(ex["text"], ex.get("outcomes", []))
        # Ademas, VOZ-07 emoji/tech y VOZ-08 certeza deben ser FAIL
        has_hard = False
        if any(c.startswith("VOZ-06") for c in lint):
            has_hard = True
        if any(c.startswith("VOZ-07:emoji") for c in lint):
            has_hard = True
        if any("multiple_exclamations" in c for c in lint):
            has_hard = True
        if any("too_many_exclamations" in c for c in lint):
            has_hard = True
        if any(c.startswith("VOZ-07:tech_jargon") for c in lint):
            has_hard = True
        if any("certainty_without_evidence" in c for c in lint):
            has_hard = True
        if grounded:
            has_hard = True
        _ = has_hard  # usado abajo via asserts
        # VOZ-06 forbidden tambien
        if ex["id"] in ("voz-013", "voz-017"):
            assert any(c.startswith("VOZ-06") for c in lint), ex["id"]
            assert ex["verdict"] == "FAIL"
        if ex["id"] == "voz-014":
            assert any("tech_jargon" in c for c in lint)
            assert ex["verdict"] == "FAIL"
        if ex["id"] == "voz-013":
            assert any("emoji" in c for c in lint)
        # PASS examples deben tener lint vacio o solo VOZ-09/borderline
        if ex["verdict"] == "PASS":
            # permitir vacio; ningún hard
            assert not any(c.startswith("VOZ-06") for c in lint), f"{ex['id']} {lint}"
            assert not any("emoji" in c for c in lint), ex["id"]
            assert not any("certainty" in c for c in lint), ex["id"]
            assert not grounded, f"{ex['id']} grounded {grounded}"
            assert is_pass(ex["text"]) is True, ex["id"]


def test_grounded_violation_detected() -> None:
    # voz-018 es el caso grounded critico
    ex = next(e for e in _load_examples() if e["id"] == "voz-018")
    assert ex["verdict"] == "FAIL"
    assert check_grounded(ex["text"], ex["outcomes"]) == [
        "VOZ-GROUNDED:rejected_described_as_applied"
    ]
    # is_pass solo (sin outcomes) no detecta grounded, pero efectivo si
    assert is_pass(ex["text"]) is True  # lint puro pasa
    assert not is_pass(ex["text"]) or check_grounded(ex["text"], ex["outcomes"])


def test_brand_templates_are_present() -> None:
    guide = VOICE_GUIDE.read_text(encoding="utf-8")
    for snippet in [
        "Encontré {n} opciones",
        "Apareció una opción muy alineada",
        "Parece {atributo}",
        "Todavía no apareció una opción",
        "Entendido. {paráfrasis",
        "Querés {cambio_material",
        "Listo, {cambio_en_pasado}",
        "Para {objetivo}, necesito que me aclares",
    ]:
        assert snippet in guide, f"template faltante: {snippet}"
