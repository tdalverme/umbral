"""The local managed-model smoke must exercise only the V5 turn interpreter."""

from __future__ import annotations

from pathlib import Path


def test_local_llm_smoke_builds_the_v5_interpreter_contract() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "local-llm-smoke.ps1"
    ).read_text(encoding="utf-8")

    assert "InterpretationCompiler" in script
    assert "TurnContext" in script
    assert "load_concepts_seed" in script
    assert "concepts-seed-v1.json" not in script
    assert "preference_interpreter" not in script
    assert "preferences_loader" not in script
