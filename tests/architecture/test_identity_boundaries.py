from __future__ import annotations

from pathlib import Path


def test_domain_identity_does_not_import_infrastructure() -> None:
    root = Path(__file__).parents[2] / "src" / "umbral" / "domain" / "identity"
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    assert "sqlalchemy" not in source
    assert "fastapi" not in source
    assert "supabase" not in source
