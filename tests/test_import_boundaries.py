import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "src" / "umbral"

FORBIDDEN = {
    "quality": {"bot", "matching"},
    "scoring": {"bot", "scrapers"},
    "ingestion": {"matching"},
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        module = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if module.startswith("umbral."):
                    found.add(module.split(".")[1])
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            if module.startswith("umbral."):
                found.add(module.split(".")[1])
    return found


def test_domain_boundaries_do_not_import_forbidden_packages():
    violations = []
    for package, forbidden in FORBIDDEN.items():
        for path in (ROOT / package).rglob("*.py"):
            imports = _imports(path)
            bad = imports & forbidden
            if bad:
                violations.append(f"{path.relative_to(ROOT)} imports {sorted(bad)}")

    assert not violations, "\n".join(violations)
